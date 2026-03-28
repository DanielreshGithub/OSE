"""
LLMProvider — abstract interface for all decision LLM backends.

Canonical action tool schema format (OpenAI function calling):
    {
        "name": "submit_action",
        "description": "...",
        "parameters": {
            "type": "object",
            "properties": {...},
            "required": [...],
        },
    }

Each provider converts this to their native format internally.
The caller (LLMDecisionActor) never touches provider-specific SDK objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


@dataclass
class ProviderCallResult:
    """
    Normalized response from any provider backend.

    `reasoning_trace` is the model-visible rationale text that OSE logs and
    later scores. It is not guaranteed to be hidden chain-of-thought; some
    providers will only expose a concise rationale field.
    """

    reasoning_trace: str
    action_dict: Optional[Dict[str, Any]]
    raw_response: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)


class LLMProvider(ABC):
    """
    Abstract LLM provider.

    Implementors: AnthropicProvider, OpenRouterProvider.

    contract:
      - call() returns ProviderCallResult
      - reasoning_trace is the model-visible rationale text
      - action_dict is the parsed tool/function call, or None on failure
      - Exceptions from the underlying SDK bubble up — caller handles retries
    """

    @abstractmethod
    def call(
        self,
        system_prompt: str,
        user_message: str,
        action_tool_schema: Dict[str, Any],
    ) -> ProviderCallResult:
        """
        Single LLM call.

        Args:
            system_prompt: Actor persona + doctrine instructions.
            user_message:  Per-turn decision prompt.
            action_tool_schema: Canonical schema dict (OpenAI function format).

        Returns:
            ProviderCallResult
        """
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """The model identifier string used in logs and DecisionRecord."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Stable provider identifier used in logs and experiment metadata."""
        ...
