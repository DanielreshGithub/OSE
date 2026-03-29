"""
Experiment Runner — orchestrates the full doctrine-condition × N-run experimental design.

Runs the simulation N times per doctrine condition across the selected conditions,
then scores all decisions and computes BCI.

Usage:
    python -m experiments.runner --runs 5 --turns 10 --scenario taiwan_strait
    python -m experiments.runner --runs 20 --turns 15 --conditions realist liberal

Output:
    logs/experiments/<experiment_id>/
        <condition>_run_<n>.db       — per-run SQLite logs
        experiment_summary.json      — aggregate statistics

Experiment cost depends on the number of doctrine conditions, runs, turns, and provider/model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv
from providers.factory import VALID_PROVIDERS, build_provider, require_provider_env

load_dotenv()

VALID_DOCTRINES = ["realist", "liberal", "org_process", "constructivist", "marxist", "baseline"]
SCENARIO_REGISTRY = {
    "taiwan_strait": "scenarios.taiwan_strait.TaiwanStraitScenario",
}


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _default_turns() -> int:
    return _env_int("OSE_DEFAULT_TURNS", 10)


def _default_seed() -> int:
    return _env_int("OSE_SCENARIO_SEED", 0)


def _load_scenario(name: str, seed: int = 0):
    if name not in SCENARIO_REGISTRY:
        print(f"Unknown scenario: {name}")
        sys.exit(1)
    import importlib
    module_path, class_name = SCENARIO_REGISTRY[name].rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)(seed=seed)


def _derive_run_seed(base_seed: int, doctrine: str, run_number: int) -> int:
    payload = f"{base_seed}:{doctrine}:{run_number}".encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") % (2**31)


def run_single(
    scenario_name: str,
    doctrine: str,
    run_number: int,
    max_turns: int,
    log_dir: str,
    experiment_id: str,
    base_seed: int,
    provider_name: str,
    model: Optional[str],
) -> Optional[str]:
    """
    Execute one simulation run. Returns the db_path on success, None on failure.
    """
    from actors.llm_actor import LLMDecisionActor
    from engine.loop import SimulationEngine

    run_id = f"{experiment_id}_{doctrine}_r{run_number:02d}"
    run_seed = _derive_run_seed(base_seed, doctrine, run_number)
    print(f"\n  [{doctrine}] Run {run_number} — {run_id}")

    try:
        scenario = _load_scenario(scenario_name, seed=run_seed)
        state = scenario.initialize()
        provider = build_provider(provider_name, model)

        # Build actors
        actors = {
            name: LLMDecisionActor(
                actor=actor,
                doctrine_condition=doctrine,
                run_id=run_id,
                provider=provider,
            )
            for name, actor in state.actors.items()
        }

        # Pass scenario directly — events roll against live state each turn
        engine = SimulationEngine(
            state=state,
            actors=actors,
            doctrine_condition=doctrine,
            run_id=run_id,
            run_number=run_number,
            seed=run_seed,
            provider_name=provider.provider_name,
            model_id=provider.model_id,
            log_dir=log_dir,
            verbose=False,   # Quiet during batch runs
            scenario=scenario,
        )

        final_state, outcome = engine.run(max_turns=max_turns)

        db_path = str(Path(log_dir) / f"{run_id}.db")
        print(f"    ✓ {outcome} | tension={final_state.global_tension:.2f} "
              f"| phase={final_state.crisis_phase} | seed={run_seed} | log={run_id}.db")
        return db_path

    except Exception as e:
        print(f"    ✗ Run failed: {e}")
        return None


def score_run(db_path: str) -> dict:
    """Score all decisions in a run database."""
    from scoring.fidelity import DoctrinesFidelityScorer
    scorer = DoctrinesFidelityScorer()
    return scorer.score_run_from_db(db_path)


def compute_bci(condition_db_map: Dict[str, List[str]]) -> dict:
    """Compute BCI across all conditions."""
    from scoring.bci import BCICalculator
    calc = BCICalculator()
    return calc.compare_conditions(condition_db_map)


def classify_outcomes(db_paths: List[str]) -> Dict[str, int]:
    """Count outcome classifications across runs."""
    import sqlite3
    counts: Dict[str, int] = {}
    for db_path in db_paths:
        if not Path(db_path).exists():
            continue
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT outcome_classification FROM runs")
        for row in cur.fetchall():
            outcome = row[0] or "unknown"
            counts[outcome] = counts.get(outcome, 0) + 1
        conn.close()
    return counts


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OSE Experiment Runner — doctrine-condition × N-run batch executor"
    )
    parser.add_argument("--scenario", default="taiwan_strait",
                        choices=list(SCENARIO_REGISTRY.keys()))
    parser.add_argument("--runs", type=int, default=5,
                        help="Number of runs per doctrine condition (default: 5)")
    parser.add_argument("--turns", type=int, default=_default_turns(),
                        help=f"Turns per run (default: {_default_turns()})")
    parser.add_argument("--conditions", nargs="+", default=VALID_DOCTRINES,
                        choices=VALID_DOCTRINES,
                        help="Doctrine conditions to run (default: all 6)")
    parser.add_argument("--experiment-id", default=None,
                        help="Experiment ID (default: auto-generated)")
    parser.add_argument("--log-dir", default="logs/experiments",
                        help="Root log directory (default: logs/experiments)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait between runs (rate limiting, default: 2)")
    parser.add_argument("--seed", type=int, default=_default_seed(),
                        help=f"Deterministic base seed for per-run derived seeds (default: {_default_seed()})")
    parser.add_argument("--provider", default="anthropic",
                        choices=VALID_PROVIDERS,
                        help="Decision LLM provider to use (default: anthropic)")
    parser.add_argument("--model", default=None,
                        help="Decision model override for the selected provider.")
    parser.add_argument("--skip-scoring", action="store_true",
                        help="Skip DFS scoring after runs (run separately later)")
    parser.add_argument("--skip-bci", action="store_true",
                        help="Skip BCI computation after runs")
    return parser


def main(argv: list[str] | None = None):
    parser = build_parser()
    args = parser.parse_args(argv)

    require_provider_env(args.provider)
    if not args.skip_scoring and not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. DFS scoring still uses Anthropic.")
        sys.exit(1)

    experiment_id = args.experiment_id or (
        f"exp_{args.scenario}_{args.provider}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
    )
    log_dir = str(Path(args.log_dir) / experiment_id)
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    total_runs = len(args.conditions) * args.runs
    est_calls = total_runs * len(["USA", "PRC", "TWN", "JPN"]) * args.turns
    print(f"\nOSE Experiment: {experiment_id}")
    print(f"  Scenario:    {args.scenario}")
    print(f"  Provider:    {args.provider}")
    print(f"  Model:       {args.model or 'provider default'}")
    print(f"  Conditions:  {args.conditions}")
    print(f"  Runs/cond:   {args.runs}")
    print(f"  Turns/run:   {args.turns}")
    print(f"  Total runs:  {total_runs}")
    print(f"  Base seed:   {args.seed}")
    if args.skip_scoring:
        print(f"  Est. LLM calls: ~{est_calls} (decision)")
    else:
        print(f"  Est. LLM calls: ~{est_calls} (decision) + ~{est_calls} (scoring)")
    print(f"  Log dir:     {log_dir}")
    print()

    # ── Execute runs ──────────────────────────────────────────────────────────
    condition_db_map: Dict[str, List[str]] = {c: [] for c in args.conditions}
    all_db_paths: List[str] = []
    run_results = []

    for condition in args.conditions:
        print(f"\n{'='*60}")
        print(f"CONDITION: {condition.upper()}")
        print(f"{'='*60}")

        for run_num in range(1, args.runs + 1):
            db_path = run_single(
                scenario_name=args.scenario,
                doctrine=condition,
                run_number=run_num,
                max_turns=args.turns,
                log_dir=log_dir,
                experiment_id=experiment_id,
                base_seed=args.seed,
                provider_name=args.provider,
                model=args.model,
            )
            if db_path:
                condition_db_map[condition].append(db_path)
                all_db_paths.append(db_path)
                run_results.append({
                    "condition": condition,
                    "run_number": run_num,
                    "db_path": db_path,
                    "seed": _derive_run_seed(args.seed, condition, run_num),
                    "success": True,
                })
            else:
                run_results.append({
                    "condition": condition,
                    "run_number": run_num,
                    "db_path": None,
                    "seed": _derive_run_seed(args.seed, condition, run_num),
                    "success": False,
                })

            if run_num < args.runs or condition != args.conditions[-1]:
                time.sleep(args.delay)

    # ── Score decisions ───────────────────────────────────────────────────────
    condition_dfs: Dict[str, dict] = {}
    if not args.skip_scoring:
        print(f"\n{'='*60}")
        print("DOCTRINE FIDELITY SCORING")
        print(f"{'='*60}")
        for condition, db_paths in condition_db_map.items():
            print(f"\nScoring condition: {condition}")
            condition_scores = []
            for db_path in db_paths:
                stats = score_run(db_path)
                if stats:
                    condition_scores.append(stats)
            if condition_scores:
                condition_dfs[condition] = {
                    "mean_language_score": round(
                        sum(s["mean_language_score"] for s in condition_scores)
                        / len(condition_scores), 3
                    ),
                    "mean_logic_score": round(
                        sum(s["mean_logic_score"] for s in condition_scores)
                        / len(condition_scores), 3
                    ),
                    "consistency_rate": round(
                        sum(s["consistency_rate"] for s in condition_scores)
                        / len(condition_scores), 3
                    ),
                    "contamination_rate": round(
                        sum(s["contamination_rate"] for s in condition_scores)
                        / len(condition_scores), 3
                    ),
                }

    # ── Compute BCI ───────────────────────────────────────────────────────────
    bci_results: dict = {}
    if not args.skip_bci:
        print(f"\n{'='*60}")
        print("BEHAVIORAL CONSISTENCY INDEX")
        print(f"{'='*60}")
        bci_results = compute_bci(condition_db_map)
        print(json.dumps(bci_results.get("summary", {}), indent=2))

    # ── Outcome classification ────────────────────────────────────────────────
    outcome_by_condition: Dict[str, dict] = {}
    for condition, db_paths in condition_db_map.items():
        outcome_by_condition[condition] = classify_outcomes(db_paths)

    # ── Write summary ─────────────────────────────────────────────────────────
    summary = {
        "experiment_id": experiment_id,
        "scenario": args.scenario,
        "conditions": args.conditions,
        "runs_per_condition": args.runs,
        "turns_per_run": args.turns,
        "completed_at": datetime.utcnow().isoformat(),
        "base_seed": args.seed,
        "run_results": run_results,
        "doctrine_fidelity_scores": condition_dfs,
        "behavioral_consistency_index": bci_results.get("summary", {}),
        "outcome_classifications": outcome_by_condition,
    }

    summary_path = Path(log_dir) / "experiment_summary.json"
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)

    # ── Final report ──────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("EXPERIMENT COMPLETE")
    print(f"{'='*60}")
    print(f"  ID:     {experiment_id}")
    print(f"  Runs:   {sum(1 for r in run_results if r['success'])}/{total_runs} successful")
    print(f"  Summary: {summary_path}")

    if condition_dfs:
        print("\n  Doctrine Fidelity Scores (mean logic score):")
        for cond, scores in condition_dfs.items():
            print(f"    {cond:15s}: logic={scores['mean_logic_score']:.3f} "
                  f"lang={scores['mean_language_score']:.3f} "
                  f"consistent={scores['consistency_rate']:.3f} "
                  f"contaminated={scores['contamination_rate']:.3f}")

    if bci_results.get("summary"):
        print("\n  Behavioral Consistency Index (lower = more consistent):")
        for cond, bci in bci_results["summary"].items():
            print(f"    {cond:15s}: BCI_action={bci.get('bci_action')} "
                  f"BCI_category={bci.get('bci_category')}")

    if outcome_by_condition:
        print("\n  Outcome distributions:")
        for cond, outcomes in outcome_by_condition.items():
            print(f"    {cond:15s}: {outcomes}")


if __name__ == "__main__":
    main()
