"""
Anthropic Claude provider for OSE.

Uses Anthropic's tool_use API with tool_choice="auto" so the model writes
free-text chain-of-thought before calling submit_action.

Schema conversion: canonical {parameters} → Anthropic {input_schema}.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

import anthropic

from providers.base import LLMProvider, ProviderCallResult

DEFAULT_MODEL = "claude-sonnet-4-6"


def _default_temperature() -> float:
    raw = os.environ.get("OSE_DEFAULT_TEMPERATURE")
    if raw in (None, ""):
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


class AnthropicProvider(LLMProvider):

    def __init__(self, model: str = DEFAULT_MODEL):
        self._model = model
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return "anthropic"

    def call(
        self,
        system_prompt: str,
        user_message: str,
        action_tool_schema: Dict[str, Any],
    ) -> ProviderCallResult:
        # Convert canonical schema (OpenAI format) → Anthropic format
        anthropic_tool = {
            "name": action_tool_schema["name"],
            "description": action_tool_schema["description"],
            "input_schema": action_tool_schema["parameters"],
        }

        response = self._client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
            tools=[anthropic_tool],
            tool_choice={"type": "auto"},
            temperature=_default_temperature(),
        )

        reasoning_parts = []
        action_dict: Optional[Dict[str, Any]] = None

        for block in response.content:
            if block.type == "text":
                reasoning_parts.append(block.text)
            elif block.type == "tool_use" and block.name == "submit_action":
                action_dict = dict(block.input)

        reasoning_trace = "\n".join(reasoning_parts)

        # Fallback: if model skipped text blocks, pull rationale from tool call
        if not reasoning_trace and action_dict:
            reasoning_trace = action_dict.get("rationale", "")

        usage = {}
        if hasattr(response, "usage") and response.usage is not None:
            usage = {
                key: getattr(response.usage, key)
                for key in (
                    "input_tokens",
                    "output_tokens",
                    "cache_creation_input_tokens",
                    "cache_read_input_tokens",
                )
                if getattr(response.usage, key, None) is not None
            }
        usage["compatibility_strategy"] = "tool_use"
        usage["finish_reason"] = getattr(response, "stop_reason", None)

        if hasattr(response, "model_dump_json"):
            raw_response = response.model_dump_json(indent=2)
        elif hasattr(response, "model_dump"):
            raw_response = json.dumps(response.model_dump(), indent=2, default=str)
        else:
            raw_response = repr(response.content)

        return ProviderCallResult(
            reasoning_trace=reasoning_trace,
            action_dict=action_dict,
            raw_response=raw_response,
            usage=usage,
        )
