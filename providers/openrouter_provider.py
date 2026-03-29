"""
OpenRouter provider for OSE.

OpenRouter exposes an OpenAI-compatible API — we use the openai SDK pointed
at https://openrouter.ai/api/v1. Most hosted models on OpenRouter support
OpenAI function calling; the schema maps 1:1 since our canonical format
IS already the OpenAI function format.

Reasoning trace: extracted from message.content (text before the tool call).
Some models write reasoning in content, others put it all in the tool call
rationale field — both cases handled.

Model strings: use OpenRouter's full model IDs, e.g.:
    openai/gpt-4o
    openai/gpt-4o-mini
    google/gemini-2.5-pro-preview
    google/gemini-2.0-flash-001
    meta-llama/llama-3.1-405b-instruct
    anthropic/claude-sonnet-4-5          (Anthropic via OpenRouter)
    mistralai/mistral-large
    x-ai/grok-3-beta
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

import openai

from providers.base import LLMProvider, ProviderCallResult

DEFAULT_MODEL = "openai/gpt-4o"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MAX_TOKENS = int(os.environ.get("OSE_OPENROUTER_MAX_TOKENS", "768"))
JSON_FALLBACK_MAX_TOKENS = int(os.environ.get("OSE_OPENROUTER_JSON_MAX_TOKENS", "256"))

# Known model capability levels — avoids paying for failed strategy attempts.
#   "tool_choice" = supports forced function call (preferred, default)
#   "tools"       = supports tools list but not forced tool_choice
#   "json"        = no tool support; use plain JSON content fallback directly
# Models not listed are assumed "tool_choice" (full capability).
MODEL_CAPABILITY_MAP: Dict[str, str] = {
    # Confirmed tool-call broken on OpenRouter as of 2026-03:
    "qwen/qwen3-235b-a22b":      "json",
    "x-ai/grok-4.2":             "json",
    # DeepSeek R1: supports tools but tool_choice=forced is unreliable:
    "deepseek/deepseek-r1-0528": "tools",
    "deepseek/deepseek-r1":      "tools",
}

# Per-model output token overrides — smaller/faster models don't need 768 tokens.
MODEL_MAX_TOKENS_MAP: Dict[str, int] = {
    "openai/gpt-4o-mini":              512,
    "google/gemini-2.0-flash-001":     512,
    "google/gemini-flash-1.5":         512,
    "meta-llama/llama-3.1-8b-instruct": 384,
}


def _default_temperature() -> float:
    raw = os.environ.get("OSE_DEFAULT_TEMPERATURE")
    if raw in (None, ""):
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _normalize_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(getattr(item, "text", "") or getattr(item, "content", "") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


def _extract_first_json_object(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None

    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate)
        candidate = re.sub(r"\s*```$", "", candidate)

    try:
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape_next = False
    for idx in range(start, len(candidate)):
        ch = candidate[idx]
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(candidate[start : idx + 1])
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    return None
    return None


def _build_json_fallback_prompt(user_message: str) -> str:
    return (
        f"{user_message}\n\n"
        "COMPATIBILITY OVERRIDE:\n"
        "Return ONLY one valid JSON object and nothing else.\n"
        "Do not include markdown, code fences, or numbered reasoning.\n"
        "Required keys: action_type, rationale.\n"
        "Optional keys: target_actor, target_zone, intensity, locality, "
        "intent_annotation, communication_mode.\n"
        "Use an action_type from the Available Actions list above.\n"
        'Example: {"action_type":"monitor","intensity":"medium","rationale":"Brief reason."}'
    )


def _error_text(exc: Exception) -> str:
    return str(exc).lower()


def _tool_choice_unsupported(exc: Exception) -> bool:
    text = _error_text(exc)
    return "tool_choice" in text and (
        "no endpoints found" in text
        or "not support" in text
        or "unsupported" in text
    )


def _tools_unsupported(exc: Exception) -> bool:
    text = _error_text(exc)
    return (
        ("tools" in text or "tool calling" in text)
        and ("not support" in text or "unsupported" in text or "no endpoints found" in text)
    )


class OpenRouterProvider(LLMProvider):

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model
        self._client = openai.OpenAI(
            api_key=os.environ["OPENROUTER_API_KEY"],
            base_url=OPENROUTER_BASE_URL,
        )

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "openrouter"

    def _capability(self) -> str:
        """Return the known capability level for this model."""
        return MODEL_CAPABILITY_MAP.get(self._model, "tool_choice")

    def _max_tokens(self) -> int:
        """Return per-model output token limit, falling back to global default."""
        return MODEL_MAX_TOKENS_MAP.get(self._model, DEFAULT_MAX_TOKENS)

    def call(
        self,
        system_prompt: str,
        user_message: str,
        action_tool_schema: Dict[str, Any],
    ) -> ProviderCallResult:
        capability = self._capability()
        max_tokens = self._max_tokens()

        tool = {
            "type": "function",
            "function": {
                "name": action_tool_schema["name"],
                "description": action_tool_schema["description"],
                "parameters": action_tool_schema["parameters"],
            },
        }

        base_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

        # Skip straight to json_content for known tool-incapable models.
        if capability == "json":
            json_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _build_json_fallback_prompt(user_message)},
            ]
            response = self._create_completion(
                messages=json_messages,
                max_tokens=JSON_FALLBACK_MAX_TOKENS,
            )
            return self._build_result(response, strategy="json_content")

        # 1. Preferred path: force a function call for strong tool-capable models.
        if capability == "tool_choice":
            try:
                response = self._create_completion(
                    messages=base_messages,
                    tools=[tool],
                    tool_choice={"type": "function", "function": {"name": "submit_action"}},
                    max_tokens=max_tokens,
                )
                result = self._build_result(response, strategy="forced_tool_choice")
                if result.action_dict is not None:
                    return result
            except Exception as exc:
                if not _tool_choice_unsupported(exc):
                    if not _tools_unsupported(exc):
                        raise
                    # tools not supported at all — drop to json_content
                    capability = "json"
                # tool_choice not supported — try auto_tools next

        if capability == "json":
            json_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": _build_json_fallback_prompt(user_message)},
            ]
            response = self._create_completion(
                messages=json_messages,
                max_tokens=JSON_FALLBACK_MAX_TOKENS,
            )
            return self._build_result(response, strategy="json_content")

        # 2. Fallback: provide tools list, let the model decide how to call.
        try:
            response = self._create_completion(
                messages=base_messages,
                tools=[tool],
                max_tokens=max_tokens,
            )
            result = self._build_result(response, strategy="auto_tools")
            if result.action_dict is not None:
                return result
        except Exception as exc:
            if not _tools_unsupported(exc):
                raise

        # 3. Last resort: plain JSON content.
        json_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _build_json_fallback_prompt(user_message)},
        ]
        response = self._create_completion(
            messages=json_messages,
            max_tokens=JSON_FALLBACK_MAX_TOKENS,
        )
        return self._build_result(response, strategy="json_content")

    def _create_completion(
        self,
        *,
        messages: list[Dict[str, str]],
        max_tokens: int,
        tools: Optional[list[Dict[str, Any]]] = None,
        tool_choice: Optional[Dict[str, Any]] = None,
    ):
        kwargs: Dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "temperature": _default_temperature(),
            "messages": messages,
        }
        if tools is not None:
            kwargs["tools"] = tools
        if tool_choice is not None:
            kwargs["tool_choice"] = tool_choice
        return self._client.chat.completions.create(**kwargs)

    def _build_result(self, response: Any, strategy: str) -> ProviderCallResult:
        message = response.choices[0].message
        reasoning_trace = _normalize_content(message.content)

        action_dict: Optional[Dict[str, Any]] = None
        if getattr(message, "tool_calls", None):
            raw_args = message.tool_calls[0].function.arguments
            try:
                action_dict = json.loads(raw_args)
            except json.JSONDecodeError:
                action_dict = None

        if action_dict is None and reasoning_trace:
            action_dict = _extract_first_json_object(reasoning_trace)

        if not reasoning_trace and action_dict:
            reasoning_trace = (
                action_dict.get("reasoning_trace")
                or action_dict.get("rationale", "")
            )

        usage = {}
        if getattr(response, "usage", None) is not None:
            usage = {
                key: getattr(response.usage, key)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if getattr(response.usage, key, None) is not None
            }
        usage["compatibility_strategy"] = strategy
        usage["finish_reason"] = getattr(response.choices[0], "finish_reason", None)

        if hasattr(response, "model_dump_json"):
            raw_response = response.model_dump_json(indent=2)
        elif hasattr(response, "model_dump"):
            raw_response = json.dumps(response.model_dump(), indent=2, default=str)
        else:
            raw_response = repr(response)

        return ProviderCallResult(
            reasoning_trace=reasoning_trace,
            action_dict=action_dict,
            raw_response=raw_response,
            usage=usage,
        )
