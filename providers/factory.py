"""
Provider factory helpers for OSE.

Keeps CLI and experiment runner aligned on provider instantiation and required
environment variables.
"""
from __future__ import annotations

import os
import sys

from providers.base import LLMProvider

VALID_PROVIDERS = ["anthropic", "openrouter"]


def build_provider(provider_name: str, model: str | None) -> LLMProvider:
    """Instantiate the requested provider backend."""
    if provider_name == "anthropic":
        from providers.anthropic_provider import AnthropicProvider, DEFAULT_MODEL

        return AnthropicProvider(model=model or DEFAULT_MODEL)

    if provider_name == "openrouter":
        from providers.openrouter_provider import OpenRouterProvider, DEFAULT_MODEL

        return OpenRouterProvider(model=model or DEFAULT_MODEL)

    print(f"Unknown provider '{provider_name}'. Available: {VALID_PROVIDERS}")
    sys.exit(1)


def require_provider_env(provider_name: str) -> None:
    """Exit with a clear message if the provider API key is missing."""
    if provider_name == "anthropic" and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    if provider_name == "openrouter" and not os.environ.get("OPENROUTER_API_KEY"):
        print("ERROR: OPENROUTER_API_KEY not set. Add OPENROUTER_API_KEY to your .env file.")
        sys.exit(1)
