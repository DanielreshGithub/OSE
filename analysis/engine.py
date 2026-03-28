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
                   crisis_phase_at_decision
            FROM decisions
            WHERE run_id = ? AND final_applied = 1
            ORDER BY turn, actor_short_name
        """, (run_id,))

        action_sequence: Dict[str, List[Dict]] = defaultdict(list)
        for turn, actor, action_json, val_result, phase in cur.fetchall():
            action_type = ""
            intensity = "medium"
            target = None
            if action_json:
                try:
                    action_dict = json.loads(action_json)
                    action_type = action_dict.get("action_type", "")
                    intensity = action_dict.get("intensity", "medium")
                    target = action_dict.get("target_actor") or action_dict.get("target_zone")
                except json.JSONDecodeError:
                    pass
            action_sequence[actor].append({
                "turn": turn,
                "action_type": action_type,
                "intensity": intensity,
                "target": target,
                "phase": phase,
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

        return {
            "n_runs": n,
            "outcomes": dict(outcomes),
            "mean_tension_trajectory": mean_tension,
            "mean_final_tension": round(mean_final, 3),
            "std_final_tension": round(std_final, 3),
            "escalation_rate": escalation,
            "action_distribution": action_dist,
            "category_distribution": category_dist,
            "aggregate_action_distribution": dict(agg_actions),
            "aggregate_category_distribution": agg_cat_frac,
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
