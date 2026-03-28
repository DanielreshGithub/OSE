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
from typing import Any, Dict, Optional

import openai

from providers.base import LLMProvider, ProviderCallResult

DEFAULT_MODEL = "openai/gpt-4o"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


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

    def call(
        self,
        system_prompt: str,
        user_message: str,
        action_tool_schema: Dict[str, Any],
    ) -> ProviderCallResult:
        # Canonical schema IS already OpenAI function format — wrap in tools list
        tool = {
            "type": "function",
            "function": {
                "name": action_tool_schema["name"],
                "description": action_tool_schema["description"],
                "parameters": action_tool_schema["parameters"],
            },
        }

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=2048,
            temperature=0,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            tools=[tool],
            tool_choice={"type": "function", "function": {"name": "submit_action"}},
        )

        message = response.choices[0].message

        # Reasoning trace — text content before the function call
        reasoning_trace = message.content or ""

        # Parse function call
        action_dict: Optional[Dict[str, Any]] = None
        if message.tool_calls:
            raw_args = message.tool_calls[0].function.arguments
            try:
                action_dict = json.loads(raw_args)
            except json.JSONDecodeError:
                action_dict = None

        # Fallback: pull reasoning from rationale if model wrote nothing in content
        if not reasoning_trace and action_dict:
            reasoning_trace = action_dict.get("rationale", "")

        usage = {}
        if getattr(response, "usage", None) is not None:
            usage = {
                key: getattr(response.usage, key)
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if getattr(response.usage, key, None) is not None
            }

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
