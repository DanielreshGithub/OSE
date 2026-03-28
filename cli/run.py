"""
OSE CLI entry point.

Usage:
    python -m cli.run --scenario taiwan_strait --turns 10 --doctrine realist
    python -m cli.run --scenario taiwan_strait --turns 15 --doctrine liberal --log-dir logs/runs
    python -m cli.run --help

Doctrine conditions: realist | liberal | org_process | baseline
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

SCENARIO_REGISTRY = {
    "taiwan_strait": "scenarios.taiwan_strait.TaiwanStraitScenario",
}

VALID_DOCTRINES = ["realist", "liberal", "org_process", "baseline"]


def load_scenario(name: str):
    """Dynamically import and instantiate a scenario class."""
    if name not in SCENARIO_REGISTRY:
        print(f"Unknown scenario '{name}'. Available: {list(SCENARIO_REGISTRY.keys())}")
        sys.exit(1)
    module_path, class_name = SCENARIO_REGISTRY[name].rsplit(".", 1)
    import importlib
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


def main():
    parser = argparse.ArgumentParser(
        description="OSE — Omni-Simulation Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Doctrine conditions:
  realist       Waltzian structural realism: relative gains, power maximization
  liberal       Keohane liberal institutionalism: interdependence, cooperation
  org_process   Allison Model II: SOPs, bureaucratic inertia, satisficing
  baseline      No doctrine prescription; actor identity only
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
        "--quiet", action="store_true",
        help="Suppress Rich terminal display",
    )

    args = parser.parse_args()

    # Check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    run_id = args.run_id or f"{args.scenario}_{args.doctrine}_{str(uuid.uuid4())[:6]}"

    # Load scenario
    scenario = load_scenario(args.scenario)
    state = scenario.initialize()

    # Build LLM actors
    from actors.llm_actor import LLMDecisionActor
    actors = {}
    for name, actor in state.actors.items():
        actors[name] = LLMDecisionActor(
            actor=actor,
            doctrine_condition=args.doctrine,
            run_id=run_id,
        )

    # Run simulation — pass scenario directly so events roll against live state each turn
    from engine.loop import SimulationEngine
    engine = SimulationEngine(
        state=state,
        actors=actors,
        doctrine_condition=args.doctrine,
        run_id=run_id,
        log_dir=args.log_dir,
        verbose=not args.quiet,
        scenario=scenario,
    )

    final_state, outcome = engine.run(max_turns=args.turns)

    print(f"\nRun complete: {run_id}")
    print(f"Outcome: {outcome}")
    print(f"Log: {args.log_dir}/{run_id}.db")
    print(f"\nQuery decisions:")
    print(f'  sqlite3 {args.log_dir}/{run_id}.db "SELECT actor_short_name, action_type, validation_result FROM decisions ORDER BY turn, actor_short_name;"')


if __name__ == "__main__":
    main()
