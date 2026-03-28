"""
Friendly top-level launcher for OSE.

Examples:
    python3 ose liberal openai/gpt-4o --turns 3
    python3 ose operator liberal model openai/gpt-4o turns 3
    python3 ose reports
    python3 ose batch --runs 5 --turns 10
"""
from __future__ import annotations

import sys
from typing import List, Tuple

from analysis.__main__ import main as analysis_main
from cli.run import SCENARIO_REGISTRY, VALID_DOCTRINES, main as run_main
from experiments.runner import main as batch_main
from providers.factory import VALID_PROVIDERS


RUN_ALIASES = {"run", "operator", "play", "simulate"}
REPORT_ALIASES = {"report", "reports", "analyze", "analysis"}
BATCH_ALIASES = {"batch", "experiment", "experiments"}

KEYWORD_FLAGS = {
    "model": "--model",
    "provider": "--provider",
    "scenario": "--scenario",
    "turns": "--turns",
    "seed": "--seed",
    "log": "--log-dir",
    "logdir": "--log-dir",
    "log-dir": "--log-dir",
}

HELP_TEXT = """OSE Launcher

Common usage:
  python3 ose liberal openai/gpt-4o --turns 3
  python3 ose operator liberal model openai/gpt-4o turns 3
  python3 ose reports
  python3 ose batch --runs 5 --turns 10

Notes:
  - A model containing '/' defaults to provider=openrouter unless you override it.
  - A Claude model without '/' defaults to provider=anthropic.
  - Existing commands still work: python3 -m cli.run ..., python3 -m analysis reports
"""


def infer_provider(model: str | None, explicit_provider: str | None = None) -> str | None:
    """Infer the provider from a model string when the user omits it."""
    if explicit_provider:
        return explicit_provider
    if not model:
        return None
    if "/" in model:
        return "openrouter"
    return "anthropic"


def build_run_argv(argv: List[str]) -> List[str]:
    """
    Translate shorthand run syntax into cli.run-style flags.

    Supported forms:
      python3 ose liberal openai/gpt-4o --turns 3
      python3 ose operator liberal model openai/gpt-4o turns 3
      python3 ose run --doctrine liberal --provider openrouter --model openai/gpt-4o
    """
    tokens = list(argv)
    doctrine = None
    provider = None
    model = None
    scenario = None
    forwarded: List[str] = []

    if tokens and tokens[0] in VALID_DOCTRINES:
        doctrine = tokens.pop(0)

    i = 0
    while i < len(tokens):
        token = tokens[i]

        if token.startswith("-"):
            forwarded.extend(tokens[i:])
            break

        if token in KEYWORD_FLAGS:
            if i + 1 >= len(tokens):
                raise SystemExit(f"Expected a value after '{token}'.")
            value = tokens[i + 1]
            flag = KEYWORD_FLAGS[token]
            if flag == "--provider":
                provider = value
            elif flag == "--model":
                model = value
            elif flag == "--scenario":
                scenario = value
            else:
                forwarded.extend([flag, value])
            i += 2
            continue

        if token in VALID_PROVIDERS and provider is None:
            provider = token
            i += 1
            continue

        if token in SCENARIO_REGISTRY and scenario is None:
            scenario = token
            i += 1
            continue

        if model is None:
            model = token
            i += 1
            continue

        forwarded.extend(tokens[i:])
        break

    provider = infer_provider(model, provider)

    normalized: List[str] = []
    if doctrine:
        normalized.extend(["--doctrine", doctrine])
    if scenario:
        normalized.extend(["--scenario", scenario])
    if provider:
        normalized.extend(["--provider", provider])
    if model:
        normalized.extend(["--model", model])
    normalized.extend(forwarded)
    return normalized


def normalize_invocation(argv: List[str]) -> Tuple[str, List[str]]:
    """Resolve the top-level command and normalized argv for its target CLI."""
    if not argv or argv[0] in {"-h", "--help", "help"}:
        return "help", []

    head = argv[0]
    tail = argv[1:]

    if head in REPORT_ALIASES:
        return "report", tail
    if head in BATCH_ALIASES:
        return "batch", tail
    if head in RUN_ALIASES:
        return "run", build_run_argv(tail)

    if (
        head in VALID_DOCTRINES
        or head in VALID_PROVIDERS
        or head in SCENARIO_REGISTRY
        or head.startswith("-")
        or "/" in head
        or head.startswith("claude")
    ):
        return "run", build_run_argv(argv)

    raise SystemExit(f"Unknown command or doctrine '{head}'.\n\n{HELP_TEXT}")


def main(argv: List[str] | None = None) -> None:
    command, normalized = normalize_invocation(list(sys.argv[1:] if argv is None else argv))

    if command == "help":
        print(HELP_TEXT)
        return
    if command == "report":
        analysis_main(normalized)
        return
    if command == "batch":
        batch_main(normalized)
        return
    run_main(normalized)


if __name__ == "__main__":
    main()
