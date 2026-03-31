"""
AnalysisEngine — extracts structured data from OSE run databases and computes
all statistical metrics needed for the research report.

No LLM calls here — pure SQL + Python. The output is a ReportData dict that
feeds into the analyst (optional LLM layer) and renderer (Markdown/LaTeX).
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from scoring.bci import ACTION_CATEGORIES, BCICalculator

# Actions considered "passive" — used to identify inflection points
PASSIVE_ACTIONS = {
    "hold_position", "monitor", "wait_and_observe", "delay_commitment",
    "defensive_posture", "signal_resolve",
}

ESCALATORY_ACTIONS = {
    "mobilize", "strike", "advance", "blockade", "deploy_forward",
    "probe", "defensive_posture", "signal_resolve", "partial_coercion",
    "cyber_operation", "hack_and_leak", "nuclear_signal",
    "targeted_sanction", "comprehensive_sanction", "embargo",
    "technology_restriction", "asset_freeze", "expel_diplomats",
}

COERCIVE_ACTIONS = {
    "mobilize", "strike", "advance", "blockade", "probe", "deploy_forward",
    "partial_coercion", "cyber_operation", "hack_and_leak", "nuclear_signal",
    "targeted_sanction", "comprehensive_sanction", "embargo",
    "technology_restriction", "asset_freeze", "cut_supply",
    "supply_chain_diversion", "expel_diplomats",
}

COOPERATIVE_ACTIONS = {
    "negotiate", "back_channel", "multilateral_appeal",
    "intel_sharing", "foreign_aid", "form_alliance",
}


class AnalysisEngine:
    """
    Extracts and analyzes data from one or more OSE run databases.
    All computation is deterministic — no LLM calls.
    """

    def analyze(self, db_paths: List[str]) -> Dict[str, Any]:
        """
        Main entry point. Accepts a list of SQLite DB paths (one per run).
        Returns the complete ReportData dict.
        """
        runs = []
        for path in db_paths:
            run = self._extract_run(path)
            if run is not None:
                runs.append(run)

        if not runs:
            return {"error": "No valid runs found."}

        runs.sort(
            key=lambda r: (
                r["doctrine"],
                r["provider_name"],
                r["model_id"],
                r["run_id"],
            )
        )

        # Group by doctrine
        by_doctrine = self._compute_doctrine_stats(runs)
        by_configuration = self._compute_configuration_stats(runs)
        by_model = self._compute_model_stats(runs)

        # Select inflection decisions for LLM analysis
        inflections = self._select_inflection_decisions(db_paths)

        # Compute BCI if multiple runs per condition
        bci = self._compute_bci(runs, db_paths)

        # Metadata
        conditions = sorted(set(r["doctrine"] for r in runs))
        scenario = runs[0]["scenario"] if runs else "unknown"
        max_turns = max(r["total_turns"] for r in runs)
        providers = sorted(set(r["provider_name"] for r in runs))
        models = sorted(set(r["model_id"] for r in runs))
        configurations = list(by_configuration.keys())
        run_inventory = [self._build_run_inventory_entry(run) for run in runs]

        return {
            "metadata": {
                "scenario": scenario,
                "conditions": conditions,
                "providers": providers,
                "models": models,
                "configurations": configurations,
                "runs_per_condition": {
                    c: sum(1 for r in runs if r["doctrine"] == c)
                    for c in conditions
                },
                "runs_per_configuration": {
                    label: stats["n_runs"]
                    for label, stats in by_configuration.items()
                },
                "total_runs": len(runs),
                "max_turns": max_turns,
                "mixed_model_report": len({(r["provider_name"], r["model_id"]) for r in runs}) > 1,
                "generated_at": datetime.utcnow().isoformat(),
            },
            "runs": runs,
            "run_inventory": run_inventory,
            "by_doctrine": by_doctrine,
            "by_configuration": by_configuration,
            "by_model": by_model,
            "bci": bci,
            "inflection_decisions": inflections,
        }

    # ── Run extraction ─────────────────────────────────────────────────────────

    def _extract_run(self, db_path: str) -> Optional[Dict[str, Any]]:
        """Extract all data from a single run database."""
        if not Path(db_path).exists():
            return None

        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        run_columns = self._table_columns(conn, "runs")
        has_provider = "provider_name" in run_columns
        has_model = "model_id" in run_columns
        has_seed = "seed" in run_columns
        has_run_number = "run_number" in run_columns

        # Run metadata
        cur.execute(
            f"""
            SELECT run_id, scenario_name, doctrine_condition,
                   {"provider_name" if has_provider else "'unknown'"},
                   {"model_id" if has_model else "'unknown'"},
                   {"seed" if has_seed else "NULL"},
                   {"run_number" if has_run_number else "NULL"},
                   total_turns, final_crisis_phase, final_global_tension,
                   outcome_classification
            FROM runs LIMIT 1
        """
        )
        row = cur.fetchone()
        if row is None:
            conn.close()
            return None

        (
            run_id,
            scenario,
            doctrine,
            provider_name,
            model_id,
            seed,
            run_number,
            total_turns,
            final_phase,
            final_tension,
            outcome,
        ) = row

        # Tension trajectory from turn_logs
        cur.execute("""
            SELECT turn, global_tension, crisis_phase
            FROM turn_logs
            WHERE run_id = ?
            ORDER BY turn
        """, (run_id,))
        turn_data = cur.fetchall()
        tension_trajectory = [(t, tension) for t, tension, _ in turn_data]
        phase_trajectory = [(t, phase) for t, _, phase in turn_data]

        # World state snapshots
        cur.execute("""
            SELECT turn, world_state_snapshot
            FROM turn_logs
            WHERE run_id = ?
            ORDER BY turn
        """, (run_id,))
        snapshots = {}
        for t, snap_json in cur.fetchall():
            try:
                snapshots[t] = json.loads(snap_json) if snap_json else {}
            except json.JSONDecodeError:
                snapshots[t] = {}

        # Action sequences per actor
        cur.execute("""
            SELECT turn, actor_short_name, parsed_action, validation_result,
                   crisis_phase_at_decision, provider_usage, retry_count
            FROM decisions
            WHERE run_id = ? AND final_applied = 1
            ORDER BY turn, actor_short_name
        """, (run_id,))

        validation_counts: Dict[str, int] = defaultdict(int)
        compatibility_strategies: Dict[str, int] = defaultdict(int)
        finish_reasons: Dict[str, int] = defaultdict(int)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        total_latency_ms = 0.0
        latency_count = 0
        retried_decisions = 0

        action_sequence: Dict[str, List[Dict]] = defaultdict(list)
        for turn, actor, action_json, val_result, phase, usage_json, retry_count in cur.fetchall():
            action_type = ""
            intensity = "medium"
            target = None
            usage = {}
            if action_json:
                try:
                    action_dict = json.loads(action_json)
                    action_type = action_dict.get("action_type", "")
                    intensity = action_dict.get("intensity", "medium")
                    target = action_dict.get("target_actor") or action_dict.get("target_zone")
                except json.JSONDecodeError:
                    pass
            if usage_json:
                try:
                    usage = json.loads(usage_json)
                except json.JSONDecodeError:
                    usage = {}
            validation_counts[val_result or "unknown"] += 1
            if retry_count:
                retried_decisions += 1

            prompt_tokens = int(
                usage.get("prompt_tokens")
                or usage.get("input_tokens")
                or 0
            )
            completion_tokens = int(
                usage.get("completion_tokens")
                or usage.get("output_tokens")
                or 0
            )
            total_token_value = usage.get("total_tokens")
            if total_token_value is None:
                total_token_value = prompt_tokens + completion_tokens
            total_prompt_tokens += prompt_tokens
            total_completion_tokens += completion_tokens
            total_tokens += int(total_token_value or 0)

            compatibility_strategy = usage.get("compatibility_strategy")
            if compatibility_strategy:
                compatibility_strategies[str(compatibility_strategy)] += 1
            finish_reason = usage.get("finish_reason")
            if finish_reason:
                finish_reasons[str(finish_reason)] += 1
            latency_ms = usage.get("decision_latency_ms") or usage.get("provider_latency_ms")
            if latency_ms is not None:
                total_latency_ms += float(latency_ms)
                latency_count += 1
            action_sequence[actor].append({
                "turn": turn,
                "action_type": action_type,
                "intensity": intensity,
                "target": target,
                "phase": phase,
                "validation_result": val_result,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": int(total_token_value or 0),
                "latency_ms": float(latency_ms) if latency_ms is not None else None,
                "compatibility_strategy": compatibility_strategy,
                "finish_reason": finish_reason,
            })

        # DFS scores if available
        cur.execute("""
            SELECT AVG(doctrine_language_score), AVG(doctrine_logic_score),
                   AVG(CAST(doctrine_consistent_decision AS REAL)),
                   AVG(CAST(contamination_flag AS REAL)),
                   COUNT(*)
            FROM decisions
            WHERE run_id = ? AND doctrine_language_score IS NOT NULL
        """, (run_id,))
        dfs_row = cur.fetchone()
        dfs = None
        if dfs_row and dfs_row[4] > 0:
            dfs = {
                "mean_language": round(dfs_row[0] or 0, 3),
                "mean_logic": round(dfs_row[1] or 0, 3),
                "consistency_rate": round(dfs_row[2] or 0, 3),
                "contamination_rate": round(dfs_row[3] or 0, 3),
                "n_scored": dfs_row[4],
            }

        # Events
        cur.execute("""
            SELECT turn, description, source, category
            FROM events
            WHERE run_id = ?
            ORDER BY turn
        """, (run_id,))
        events = [
            {"turn": t, "description": d, "source": s, "category": c}
            for t, d, s, c in cur.fetchall()
        ]

        conn.close()

        run_label = self._run_label(
            doctrine=doctrine,
            provider_name=provider_name or "unknown",
            model_id=model_id or "unknown",
            run_id=run_id,
        )

        return {
            "run_id": run_id,
            "run_label": run_label,
            "db_path": db_path,
            "scenario": scenario,
            "doctrine": doctrine,
            "provider_name": provider_name or "unknown",
            "model_id": model_id or "unknown",
            "seed": seed,
            "run_number": run_number,
            "total_turns": total_turns or len(tension_trajectory),
            "outcome": outcome or "unknown",
            "final_tension": final_tension or 0.0,
            "final_phase": final_phase or "unknown",
            "tension_trajectory": tension_trajectory,
            "phase_trajectory": phase_trajectory,
            "snapshots": snapshots,
            "action_sequence": dict(action_sequence),
            "events": events,
            "dfs": dfs,
            "operational_metrics": {
                "total_decisions": sum(validation_counts.values()),
                "validation_results": dict(validation_counts),
                "valid_decisions": int(validation_counts.get("valid", 0) + validation_counts.get("retry_valid", 0)),
                "skipped_decisions": int(validation_counts.get("skipped", 0)),
                "retried_decisions": retried_decisions,
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_tokens": total_tokens,
                "avg_prompt_tokens_per_decision": round(total_prompt_tokens / max(sum(validation_counts.values()), 1), 2),
                "avg_completion_tokens_per_decision": round(total_completion_tokens / max(sum(validation_counts.values()), 1), 2),
                "avg_total_tokens_per_decision": round(total_tokens / max(sum(validation_counts.values()), 1), 2),
                "avg_latency_ms": round(total_latency_ms / latency_count, 2) if latency_count else None,
                "total_latency_ms": round(total_latency_ms, 2),
                "compatibility_strategies": dict(compatibility_strategies),
                "finish_reasons": dict(finish_reasons),
            },
        }

    # ── Doctrine-level statistics ──────────────────────────────────────────────

    def _compute_doctrine_stats(
        self, runs: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Compute aggregate statistics grouped by doctrine condition."""
        by_doctrine: Dict[str, List[Dict]] = defaultdict(list)
        for run in runs:
            by_doctrine[run["doctrine"]].append(run)

        return {
            doctrine: self._summarize_run_group(doctrine_runs)
            for doctrine, doctrine_runs in by_doctrine.items()
        }

    def _compute_configuration_stats(
        self, runs: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Compute aggregate statistics for each doctrine+provider+model configuration."""
        by_configuration: Dict[Tuple[str, str, str], List[Dict[str, Any]]] = defaultdict(list)
        for run in runs:
            by_configuration[
                (run["doctrine"], run["provider_name"], run["model_id"])
            ].append(run)

        result: Dict[str, Dict[str, Any]] = {}
        for (doctrine, provider_name, model_id), config_runs in sorted(
            by_configuration.items(),
            key=lambda item: (item[0][0], item[0][1], item[0][2]),
        ):
            label = self._configuration_label(doctrine, provider_name, model_id)
            stats = self._summarize_run_group(config_runs)
            stats.update(
                {
                    "doctrine": doctrine,
                    "provider_name": provider_name,
                    "model_id": model_id,
                    "label": label,
                }
            )
            result[label] = stats

        return result

    def _compute_model_stats(
        self, runs: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Compute provider/model aggregate stats across doctrines."""
        by_model: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
        for run in runs:
            by_model[(run["provider_name"], run["model_id"])].append(run)

        result: Dict[str, Dict[str, Any]] = {}
        for (provider_name, model_id), model_runs in sorted(
            by_model.items(),
            key=lambda item: (item[0][0], item[0][1]),
        ):
            per_doctrine: Dict[str, Dict[str, Any]] = {}
            for doctrine, doctrine_runs in defaultdict(list, {
                doctrine: [run for run in model_runs if run["doctrine"] == doctrine]
                for doctrine in sorted({run["doctrine"] for run in model_runs})
            }).items():
                per_doctrine[doctrine] = self._summarize_run_group(doctrine_runs)

            separation = self._compute_doctrine_separation(per_doctrine)
            label = f"{provider_name} | {model_id}"
            result[label] = {
                "provider_name": provider_name,
                "model_id": model_id,
                "n_runs": len(model_runs),
                "doctrines_covered": sorted(per_doctrine.keys()),
                "operational_metrics": self._aggregate_operational_metrics(model_runs),
                "doctrine_separation": separation,
                "per_doctrine": {
                    doctrine: {
                        "mean_final_tension": stats["mean_final_tension"],
                        "outcomes": stats["outcomes"],
                        "aggregate_category_distribution": stats.get("aggregate_category_distribution", {}),
                    }
                    for doctrine, stats in per_doctrine.items()
                },
            }

        return result

    def _summarize_run_group(self, group_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate shared statistics for a homogeneous run group."""
        n = len(group_runs)

        outcomes: Dict[str, int] = defaultdict(int)
        for run in group_runs:
            outcomes[run["outcome"]] += 1

        mean_tension = self._mean_tension_trajectory(group_runs)
        final_tensions = [r["final_tension"] for r in group_runs]
        mean_final = sum(final_tensions) / n
        std_final = _std(final_tensions) if n > 1 else 0.0
        turns_to_terminal = [r["total_turns"] for r in group_runs]
        escalation = self._compute_escalation_rate(group_runs)
        action_dist, category_dist = self._compute_action_distributions(group_runs)

        agg_actions: Dict[str, int] = defaultdict(int)
        agg_categories: Dict[str, int] = defaultdict(int)
        for actor_actions in action_dist.values():
            for action, count in actor_actions.items():
                agg_actions[action] += count
                cat = ACTION_CATEGORIES.get(action, "unknown")
                agg_categories[cat] += count

        total_actions = sum(agg_categories.values()) or 1
        agg_cat_frac = {
            k: round(v / total_actions, 3) for k, v in agg_categories.items()
        }

        dfs_runs = [r["dfs"] for r in group_runs if r["dfs"] is not None]
        dfs_agg = None
        if dfs_runs:
            dfs_agg = {
                "mean_language": round(
                    sum(d["mean_language"] for d in dfs_runs) / len(dfs_runs), 3
                ),
                "mean_logic": round(
                    sum(d["mean_logic"] for d in dfs_runs) / len(dfs_runs), 3
                ),
                "consistency_rate": round(
                    sum(d["consistency_rate"] for d in dfs_runs) / len(dfs_runs), 3
                ),
                "contamination_rate": round(
                    sum(d["contamination_rate"] for d in dfs_runs) / len(dfs_runs), 3
                ),
            }

        outcome_probabilities = {
            outcome: round(count / n, 3)
            for outcome, count in sorted(outcomes.items())
        }
        actor_profiles = self._aggregate_actor_profiles(group_runs)
        operational_metrics = self._aggregate_operational_metrics(group_runs)

        return {
            "n_runs": n,
            "outcomes": dict(outcomes),
            "outcome_probabilities": outcome_probabilities,
            "war_probability": outcome_probabilities.get("deterrence_failure", 0.0),
            "peace_probability": outcome_probabilities.get("deterrence_success", 0.0),
            "frozen_conflict_probability": outcome_probabilities.get("frozen_conflict", 0.0),
            "mean_tension_trajectory": mean_tension,
            "mean_final_tension": round(mean_final, 3),
            "std_final_tension": round(std_final, 3),
            "mean_turns_to_terminal": round(sum(turns_to_terminal) / n, 2),
            "std_turns_to_terminal": round(_std(turns_to_terminal), 3) if n > 1 else 0.0,
            "terminal_turn_distribution": {
                str(turn): turns_to_terminal.count(turn)
                for turn in sorted(set(turns_to_terminal))
            },
            "escalation_rate": escalation,
            "action_distribution": action_dist,
            "category_distribution": category_dist,
            "aggregate_action_distribution": dict(agg_actions),
            "aggregate_category_distribution": agg_cat_frac,
            "actor_profiles": actor_profiles,
            "operational_metrics": operational_metrics,
            "dfs": dfs_agg,
        }

    def _mean_tension_trajectory(
        self, runs: List[Dict]
    ) -> List[Tuple[int, float, float]]:
        """Compute mean ± std tension at each turn across runs."""
        by_turn: Dict[int, List[float]] = defaultdict(list)
        for run in runs:
            for turn, tension in run["tension_trajectory"]:
                by_turn[turn].append(tension)

        result = []
        for turn in sorted(by_turn.keys()):
            values = by_turn[turn]
            mean = sum(values) / len(values)
            std = _std(values) if len(values) > 1 else 0.0
            result.append((turn, round(mean, 3), round(std, 3)))
        return result

    def _compute_escalation_rate(self, runs: List[Dict]) -> Dict[str, Any]:
        """Compute mean turns to reach crisis and war phases."""
        turns_to_crisis = []
        turns_to_war = []

        for run in runs:
            crisis_turn = None
            war_turn = None
            for turn, phase in run["phase_trajectory"]:
                if phase in ("crisis", "war") and crisis_turn is None:
                    crisis_turn = turn
                if phase == "war" and war_turn is None:
                    war_turn = turn
            if crisis_turn is not None:
                turns_to_crisis.append(crisis_turn)
            if war_turn is not None:
                turns_to_war.append(war_turn)

        return {
            "mean_turns_to_crisis": round(
                sum(turns_to_crisis) / len(turns_to_crisis), 1
            ) if turns_to_crisis else None,
            "mean_turns_to_war": round(
                sum(turns_to_war) / len(turns_to_war), 1
            ) if turns_to_war else None,
            "pct_reaching_war": round(
                len(turns_to_war) / len(runs), 3
            ) if runs else 0.0,
            "pct_reaching_crisis": round(
                len(turns_to_crisis) / len(runs), 3
            ) if runs else 0.0,
        }

    def _compute_action_distributions(
        self, runs: List[Dict]
    ) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, float]]]:
        """
        Returns:
          action_dist: {actor: {action_type: count}}
          category_dist: {actor: {category: fraction}}
        """
        action_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for run in runs:
            for actor, actions in run["action_sequence"].items():
                for a in actions:
                    action_counts[actor][a["action_type"]] += 1

        category_dist: Dict[str, Dict[str, float]] = {}
        for actor, counts in action_counts.items():
            cat_counts: Dict[str, int] = defaultdict(int)
            total = sum(counts.values()) or 1
            for action, count in counts.items():
                cat = ACTION_CATEGORIES.get(action, "unknown")
                cat_counts[cat] += count
            category_dist[actor] = {
                k: round(v / total, 3) for k, v in cat_counts.items()
            }

        return dict(action_counts), category_dist

    def _aggregate_actor_profiles(
        self, runs: List[Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        profiles: Dict[str, Dict[str, List[Any]]] = defaultdict(lambda: defaultdict(list))
        for run in runs:
            for actor, actions in run["action_sequence"].items():
                first_escalatory = self._first_matching_action(actions, ESCALATORY_ACTIONS)
                first_coercive = self._first_matching_action(actions, COERCIVE_ACTIONS)
                first_cooperative = self._first_matching_action(actions, COOPERATIVE_ACTIONS)
                if first_escalatory:
                    profiles[actor]["escalatory_turns"].append(first_escalatory["turn"])
                    profiles[actor]["escalatory_actions"].append(first_escalatory["action_type"])
                if first_coercive:
                    profiles[actor]["coercive_turns"].append(first_coercive["turn"])
                    profiles[actor]["coercive_actions"].append(first_coercive["action_type"])
                if first_cooperative:
                    profiles[actor]["cooperative_turns"].append(first_cooperative["turn"])
                    profiles[actor]["cooperative_actions"].append(first_cooperative["action_type"])

        result: Dict[str, Dict[str, Any]] = {}
        total_runs = len(runs) or 1
        for actor, profile in profiles.items():
            result[actor] = {
                "escalatory_rate": round(len(profile.get("escalatory_turns", [])) / total_runs, 3),
                "coercive_rate": round(len(profile.get("coercive_turns", [])) / total_runs, 3),
                "cooperative_rate": round(len(profile.get("cooperative_turns", [])) / total_runs, 3),
                "mean_first_escalatory_turn": round(sum(profile["escalatory_turns"]) / len(profile["escalatory_turns"]), 2)
                if profile.get("escalatory_turns") else None,
                "mean_first_coercive_turn": round(sum(profile["coercive_turns"]) / len(profile["coercive_turns"]), 2)
                if profile.get("coercive_turns") else None,
                "mean_first_cooperative_turn": round(sum(profile["cooperative_turns"]) / len(profile["cooperative_turns"]), 2)
                if profile.get("cooperative_turns") else None,
                "most_common_first_escalatory_action": _mode(profile.get("escalatory_actions", [])),
                "most_common_first_coercive_action": _mode(profile.get("coercive_actions", [])),
                "most_common_first_cooperative_action": _mode(profile.get("cooperative_actions", [])),
            }
        return result

    def _aggregate_operational_metrics(
        self, runs: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        total_decisions = 0
        valid_decisions = 0
        skipped_decisions = 0
        retried_decisions = 0
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        total_latency_ms = 0.0
        latency_count = 0
        validation_results: Dict[str, int] = defaultdict(int)
        compatibility_strategies: Dict[str, int] = defaultdict(int)
        finish_reasons: Dict[str, int] = defaultdict(int)

        for run in runs:
            metrics = run.get("operational_metrics", {})
            total_decisions += int(metrics.get("total_decisions", 0))
            valid_decisions += int(metrics.get("valid_decisions", 0))
            skipped_decisions += int(metrics.get("skipped_decisions", 0))
            retried_decisions += int(metrics.get("retried_decisions", 0))
            total_prompt_tokens += int(metrics.get("total_prompt_tokens", 0))
            total_completion_tokens += int(metrics.get("total_completion_tokens", 0))
            total_tokens += int(metrics.get("total_tokens", 0))
            if metrics.get("avg_latency_ms") is not None:
                weighted_latency = float(metrics.get("avg_latency_ms", 0.0)) * int(metrics.get("total_decisions", 0))
                total_latency_ms += weighted_latency
                latency_count += int(metrics.get("total_decisions", 0))
            for key, value in metrics.get("validation_results", {}).items():
                validation_results[key] += int(value)
            for key, value in metrics.get("compatibility_strategies", {}).items():
                compatibility_strategies[key] += int(value)
            for key, value in metrics.get("finish_reasons", {}).items():
                finish_reasons[key] += int(value)

        valid_rate = round(valid_decisions / total_decisions, 3) if total_decisions else 0.0
        skipped_rate = round(skipped_decisions / total_decisions, 3) if total_decisions else 0.0
        retry_rate = round(retried_decisions / total_decisions, 3) if total_decisions else 0.0
        avg_latency_ms = round(total_latency_ms / latency_count, 2) if latency_count else None
        avg_tokens = round(total_tokens / total_decisions, 2) if total_decisions else 0.0

        admission_status = "admit"
        admission_notes: List[str] = []
        if valid_rate < 0.95 or skipped_rate > 0.05:
            admission_status = "caution"
            admission_notes.append("Validation/fallback rate suggests partial compatibility risk.")
        if valid_rate < 0.80 or skipped_rate > 0.20:
            admission_status = "exclude"
            admission_notes.append("Decision validity is too weak for benchmark-quality runs.")
        if avg_latency_ms is not None and avg_latency_ms > 20000:
            admission_status = "caution" if admission_status == "admit" else admission_status
            admission_notes.append("Average decision latency is high enough to slow repeated-run batches.")

        return {
            "total_decisions": total_decisions,
            "valid_decisions": valid_decisions,
            "skipped_decisions": skipped_decisions,
            "retried_decisions": retried_decisions,
            "valid_decision_rate": valid_rate,
            "skipped_decision_rate": skipped_rate,
            "retry_rate": retry_rate,
            "total_prompt_tokens": total_prompt_tokens,
            "total_completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
            "avg_prompt_tokens_per_decision": round(total_prompt_tokens / total_decisions, 2) if total_decisions else 0.0,
            "avg_completion_tokens_per_decision": round(total_completion_tokens / total_decisions, 2) if total_decisions else 0.0,
            "avg_total_tokens_per_decision": avg_tokens,
            "avg_latency_ms": avg_latency_ms,
            "validation_results": dict(validation_results),
            "compatibility_strategies": dict(sorted(compatibility_strategies.items())),
            "finish_reasons": dict(sorted(finish_reasons.items())),
            "admission_status": admission_status,
            "admission_notes": admission_notes,
        }

    def _compute_doctrine_separation(
        self, per_doctrine: Dict[str, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        if len(per_doctrine) < 2:
            return None

        doctrine_names = sorted(per_doctrine.keys())
        pairwise_category_distances: List[float] = []
        for idx, left_name in enumerate(doctrine_names):
            for right_name in doctrine_names[idx + 1:]:
                left = per_doctrine[left_name].get("aggregate_category_distribution", {})
                right = per_doctrine[right_name].get("aggregate_category_distribution", {})
                pairwise_category_distances.append(_total_variation_distance(left, right))

        tensions = [float(stats["mean_final_tension"]) for stats in per_doctrine.values()]
        tension_range = max(tensions) - min(tensions) if tensions else 0.0
        dominant_outcomes = {
            max(stats.get("outcomes", {}).items(), key=lambda item: item[1])[0]
            for stats in per_doctrine.values()
            if stats.get("outcomes")
        }
        outcome_diversity = (
            (len(dominant_outcomes) - 1) / max(len(per_doctrine) - 1, 1)
            if dominant_outcomes else 0.0
        )
        avg_pairwise_distance = (
            sum(pairwise_category_distances) / len(pairwise_category_distances)
            if pairwise_category_distances else 0.0
        )
        score = min(
            1.0,
            (0.6 * avg_pairwise_distance) + (0.3 * tension_range) + (0.1 * outcome_diversity),
        )

        return {
            "score": round(score, 3),
            "avg_pairwise_category_distance": round(avg_pairwise_distance, 3),
            "tension_range": round(tension_range, 3),
            "dominant_outcome_diversity": round(outcome_diversity, 3),
        }

    def _first_matching_action(
        self, actions: List[Dict[str, Any]], candidates: set[str]
    ) -> Optional[Dict[str, Any]]:
        for action in actions:
            if action.get("action_type") in candidates:
                return action
        return None

    # ── Inflection decision selection ──────────────────────────────────────────

    def _select_inflection_decisions(
        self, db_paths: List[str], max_per_run: int = 6
    ) -> List[Dict[str, Any]]:
        """
        Select inflection-point decisions for LLM analysis.

        Selection criteria (priority order):
          1. First non-passive action per actor per run
          2. Decision at the turn where crisis phase escalated
          3. Decisions flagged as contaminated
          4. Final decision per actor per run (if different from above)
        """
        inflections = []

        for db_path in db_paths:
            if not Path(db_path).exists():
                continue
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()

            # Get run metadata
            run_columns = self._table_columns(conn, "runs")
            cur.execute(
                f"""
                SELECT run_id, doctrine_condition,
                       {"provider_name" if "provider_name" in run_columns else "'unknown'"},
                       {"model_id" if "model_id" in run_columns else "'unknown'"}
                FROM runs LIMIT 1
            """
            )
            row = cur.fetchone()
            if row is None:
                conn.close()
                continue
            run_id, doctrine, provider_name, model_id = row

            # Get phase transitions
            cur.execute("""
                SELECT turn, crisis_phase FROM turn_logs
                WHERE run_id = ? ORDER BY turn
            """, (run_id,))
            phase_log = cur.fetchall()
            phase_transition_turns = set()
            for i in range(1, len(phase_log)):
                if phase_log[i][1] != phase_log[i - 1][1]:
                    phase_transition_turns.add(phase_log[i][0])

            # Get all applied decisions with traces
            cur.execute("""
                SELECT id, turn, actor_short_name, parsed_action,
                       reasoning_trace, crisis_phase_at_decision,
                       contamination_flag
                FROM decisions
                WHERE run_id = ? AND final_applied = 1
                ORDER BY turn, actor_short_name
            """, (run_id,))
            decisions = cur.fetchall()
            conn.close()

            selected_ids = set()
            run_inflections = []

            # Track first non-passive per actor
            first_active: Dict[str, bool] = {}

            for dec_id, turn, actor, action_json, trace, phase, contaminated in decisions:
                action_type = ""
                if action_json:
                    try:
                        action_type = json.loads(action_json).get("action_type", "")
                    except json.JSONDecodeError:
                        pass

                reason = None

                # First non-passive action per actor
                if actor not in first_active and action_type not in PASSIVE_ACTIONS and action_type:
                    first_active[actor] = True
                    reason = f"First active action by {actor}"

                # Phase transition turn
                if turn in phase_transition_turns and reason is None:
                    reason = f"Crisis phase transition at turn {turn}"

                # Contaminated decision
                if contaminated and reason is None:
                    reason = "Doctrine contamination flagged"

                if reason and dec_id not in selected_ids and trace:
                    selected_ids.add(dec_id)
                    run_inflections.append({
                        "run_id": run_id,
                        "run_label": self._run_label(
                            doctrine=doctrine,
                            provider_name=provider_name or "unknown",
                            model_id=model_id or "unknown",
                            run_id=run_id,
                        ),
                        "doctrine": doctrine,
                        "provider_name": provider_name or "unknown",
                        "model_id": model_id or "unknown",
                        "turn": turn,
                        "actor": actor,
                        "action_type": action_type,
                        "reasoning_trace": trace,
                        "crisis_phase": phase,
                        "selection_reason": reason,
                    })

            final_by_actor: Dict[str, Tuple[int, int, str, str, str]] = {}
            for dec_id, turn, actor, action_json, trace, phase, _ in reversed(decisions):
                if actor in final_by_actor:
                    continue
                action_type = ""
                if action_json:
                    try:
                        action_type = json.loads(action_json).get("action_type", "")
                    except json.JSONDecodeError:
                        pass
                final_by_actor[actor] = (dec_id, turn, action_type, trace, phase)

            for actor, (dec_id, turn, action_type, trace, phase) in sorted(final_by_actor.items()):
                if dec_id in selected_ids or not trace:
                    continue
                selected_ids.add(dec_id)
                run_inflections.append({
                    "run_id": run_id,
                    "run_label": self._run_label(
                        doctrine=doctrine,
                        provider_name=provider_name or "unknown",
                        model_id=model_id or "unknown",
                        run_id=run_id,
                    ),
                    "doctrine": doctrine,
                    "provider_name": provider_name or "unknown",
                    "model_id": model_id or "unknown",
                    "turn": turn,
                    "actor": actor,
                    "action_type": action_type,
                    "reasoning_trace": trace,
                    "crisis_phase": phase,
                    "selection_reason": f"Final decision by {actor}",
                })

            # Cap per run
            inflections.extend(run_inflections[:max_per_run])

        return inflections

    # ── BCI computation ────────────────────────────────────────────────────────

    def _compute_bci(
        self, runs: List[Dict], db_paths: List[str]
    ) -> Optional[Dict]:
        """Compute BCI if there are multiple runs per doctrine condition."""
        unique_model_configs = {
            (run["provider_name"], run["model_id"])
            for run in runs
        }
        if len(unique_model_configs) > 1:
            return None

        condition_db_map: Dict[str, List[str]] = defaultdict(list)
        for run in runs:
            condition_db_map[run["doctrine"]].append(run["db_path"])

        # Only compute if at least one condition has 2+ runs
        if not any(len(paths) >= 2 for paths in condition_db_map.values()):
            return None

        calc = BCICalculator()
        return calc.compare_conditions(dict(condition_db_map))

    def _table_columns(self, conn: sqlite3.Connection, table: str) -> set[str]:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table})")
        return {row[1] for row in cur.fetchall()}

    def _build_run_inventory_entry(self, run: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "run_id": run["run_id"],
            "run_label": run["run_label"],
            "doctrine": run["doctrine"],
            "provider_name": run["provider_name"],
            "model_id": run["model_id"],
            "seed": run.get("seed"),
            "run_number": run.get("run_number"),
            "outcome": run["outcome"],
            "total_turns": run["total_turns"],
            "final_phase": run["final_phase"],
            "final_tension": run["final_tension"],
        }

    def _configuration_label(
        self,
        doctrine: str,
        provider_name: str,
        model_id: str,
    ) -> str:
        return f"{doctrine} | {provider_name} | {model_id}"

    def _run_label(
        self,
        doctrine: str,
        provider_name: str,
        model_id: str,
        run_id: str,
    ) -> str:
        return f"{doctrine} | {provider_name} | {model_id} | {run_id}"


def _std(values: List[float]) -> float:
    """Population standard deviation."""
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    return round(math.sqrt(variance), 3)


def _mode(values: List[str]) -> Optional[str]:
    if not values:
        return None
    counts: Dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _total_variation_distance(
    left: Dict[str, float], right: Dict[str, float]
) -> float:
    keys = set(left) | set(right)
    return 0.5 * sum(abs(float(left.get(key, 0.0)) - float(right.get(key, 0.0))) for key in keys)
