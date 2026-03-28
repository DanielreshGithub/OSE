"""
OSE CLI entry point.

Usage:
    python -m cli.run --scenario taiwan_strait --turns 10 --doctrine realist
    python -m cli.run --scenario taiwan_strait --turns 10 --doctrine liberal --provider openrouter --model openai/gpt-4o
    python -m cli.run --scenario taiwan_strait --turns 10 --provider openrouter --model google/gemini-2.5-pro-preview
    python -m cli.run --help

Doctrine conditions: realist | liberal | org_process | constructivist | marxist | baseline
Providers: anthropic | openrouter
"""
from __future__ import annotations

import argparse
import sys
import uuid

from dotenv import load_dotenv
from providers.factory import VALID_PROVIDERS, build_provider, require_provider_env

load_dotenv()

SCENARIO_REGISTRY = {
    "taiwan_strait": "scenarios.taiwan_strait.TaiwanStraitScenario",
}

VALID_DOCTRINES = ["realist", "liberal", "org_process", "constructivist", "marxist", "baseline"]


def load_scenario(name: str, seed: int = 0):
    """Dynamically import and instantiate a scenario class."""
    if name not in SCENARIO_REGISTRY:
        print(f"Unknown scenario '{name}'. Available: {list(SCENARIO_REGISTRY.keys())}")
        sys.exit(1)
    module_path, class_name = SCENARIO_REGISTRY[name].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)(seed=seed)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OSE — Omni-Simulation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Doctrine conditions:
  realist       Waltzian structural realism: relative gains, power maximization
  liberal       Keohane liberal institutionalism: interdependence, cooperation
  org_process   Allison Model II: SOPs, bureaucratic inertia, satisficing
  constructivist Identity and legitimacy: norms, role, reputation, signaling
  marxist       Structural dependency: capital autonomy, hierarchy, anti-hegemonic leverage
  baseline      Allison Model I rational actor: explicit expected utility optimization
        """,
    )
    parser.add_argument(
        "--scenario", default="taiwan_strait",
        choices=list(SCENARIO_REGISTRY.keys()),
        help="Scenario to run (default: taiwan_strait)",
    )
    parser.add_argument(
        "--turns", type=int, default=10,
        help="Maximum number of turns (default: 10)",
    )
    parser.add_argument(
        "--doctrine", default="baseline",
        choices=VALID_DOCTRINES,
        help="Decision doctrine condition (default: baseline)",
    )
    parser.add_argument(
        "--log-dir", default="logs/runs",
        help="Directory for SQLite run logs (default: logs/runs)",
    )
    parser.add_argument(
        "--run-id", default=None,
        help="Run ID override (default: auto-generated)",
    )
    parser.add_argument(
        "--seed", type=int, default=0,
        help="Deterministic seed for scenario evolution and perception (default: 0)",
    )
    parser.add_argument(
        "--provider", default="anthropic",
        choices=VALID_PROVIDERS,
        help="LLM provider to use (default: anthropic)",
    )
    parser.add_argument(
        "--model", default=None,
        help="Model ID override (default: provider's default model). "
             "Anthropic: claude-sonnet-4-6. "
             "OpenRouter: openai/gpt-4o, google/gemini-2.5-pro-preview, meta-llama/llama-3.1-405b-instruct, etc.",
    )
    parser.add_argument(
        "--quiet", action="store_true",
        help="Suppress Rich terminal display",
    )
    return parser


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    # Build provider
    require_provider_env(args.provider)
    provider = build_provider(args.provider, args.model)
    provider_slug = provider.provider_name.replace("/", "_")
    model_slug = provider.model_id.split("/")[-1].replace(":", "_")
    run_id = args.run_id or f"{args.scenario}_{args.doctrine}_{provider_slug}_{model_slug}_{str(uuid.uuid4())[:6]}"

    # Load scenario
    scenario = load_scenario(args.scenario, seed=args.seed)
    state = scenario.initialize()

    # Build LLM actors — all share the same provider instance
    from actors.llm_actor import LLMDecisionActor
    actors = {}
    for name, actor in state.actors.items():
        actors[name] = LLMDecisionActor(
            actor=actor,
            doctrine_condition=args.doctrine,
            run_id=run_id,
            provider=provider,
        )

    # Run simulation — pass scenario directly so events roll against live state each turn
    from engine.loop import SimulationEngine
    engine = SimulationEngine(
        state=state,
        actors=actors,
        doctrine_condition=args.doctrine,
        run_id=run_id,
        run_number=1,
        seed=args.seed,
        provider_name=provider.provider_name,
        model_id=provider.model_id,
        log_dir=args.log_dir,
        verbose=not args.quiet,
        scenario=scenario,
    )

    final_state, outcome = engine.run(max_turns=args.turns)

    print(f"\nRun complete: {run_id}")
    print(f"Outcome: {outcome}")
    print(f"Seed: {args.seed}")
    print(f"Provider: {provider.provider_name}")
    print(f"Model: {provider.model_id}")
    print(f"Log: {args.log_dir}/{run_id}.db")
    print(f"\nQuery decisions:")
    print(
        f"  sqlite3 {args.log_dir}/{run_id}.db "
        "\"SELECT turn, actor_short_name, provider_name, model_id, "
        "json_extract(parsed_action, '$.action_type') AS action_type, validation_result "
        "FROM decisions ORDER BY turn, actor_short_name;\""
    )


if __name__ == "__main__":
    main()
