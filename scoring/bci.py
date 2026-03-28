"""
Behavioral Consistency Index (BCI) — measures action distribution variance
across repeated runs of the same doctrine condition.

BCI answers: given the same doctrine and scenario, how consistently does
the LLM choose the same category of action across N runs?

Low BCI (near 0.0) = highly consistent — the doctrine reliably channels behavior.
High BCI (near 1.0) = high variance — behavior is stochastic despite prescription.

Computed per actor, per doctrine condition, aggregated across runs.

Methodology:
  - For each actor × turn × doctrine_condition, collect action_types across N runs
  - Compute normalized entropy of the action distribution
  - Average over turns to get per-actor BCI
  - Average over actors to get run-level BCI

Normalized entropy: H / log2(|action_space|)
  = 0.0  if actor always picks the same action
  = 1.0  if actor picks uniformly across all 23 actions

We also compute BCI at the CATEGORY level (military / diplomatic / economic /
information / inaction) for coarser but more interpretable analysis.
"""
from __future__ import annotations

import json
import math
import sqlite3
from collections import defaultdict
from typing import Dict, List, Optional

ACTION_CATEGORIES = {
    # Military (8)
    "mobilize": "military",
    "strike": "military",
    "advance": "military",
    "withdraw": "military",
    "blockade": "military",
    "defensive_posture": "military",
    "probe": "military",
    "signal_resolve": "military",
    # Diplomatic (7)
    "negotiate": "diplomatic",
    "targeted_sanction": "diplomatic",
    "comprehensive_sanction": "diplomatic",
    "form_alliance": "diplomatic",
    "condemn": "diplomatic",
    "intel_sharing": "diplomatic",
    "back_channel": "diplomatic",
    # Economic (4)
    "embargo": "economic",
    "foreign_aid": "economic",
    "cut_supply": "economic",
    "technology_restriction": "economic",
    # Information / Cyber (3)
    "propaganda": "information",
    "partial_coercion": "information",
    "cyber_operation": "information",
    # Nuclear (1)
    "nuclear_signal": "nuclear",
    # Inaction (2)
    "hold_position": "inaction",
    "monitor": "inaction",
}

N_ACTIONS = len(ACTION_CATEGORIES)
N_CATEGORIES = 6  # military, diplomatic, economic, information, nuclear, inaction


def _entropy(counts: Dict[str, int]) -> float:
    """Shannon entropy of a frequency distribution."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum(
        (c / total) * math.log2(c / total)
        for c in counts.values()
        if c > 0
    )


def _normalized_entropy(counts: Dict[str, int], n_outcomes: int) -> float:
    """Entropy normalized to [0, 1] by log2(n_outcomes)."""
    if n_outcomes <= 1:
        return 0.0
    max_entropy = math.log2(n_outcomes)
    return _entropy(counts) / max_entropy


class BCICalculator:
    """
    Computes Behavioral Consistency Index from one or more SQLite run logs
    belonging to the same doctrine condition.
    """

    def compute_from_db(
        self,
        db_paths: List[str],
        doctrine_condition: str,
    ) -> Dict:
        """
        Compute BCI from a list of run databases (same doctrine condition).
        Returns a dict of BCI metrics.
        """
        # Collect: actor -> turn -> [action_type, ...]
        action_log: Dict[str, Dict[int, List[str]]] = defaultdict(lambda: defaultdict(list))

        for db_path in db_paths:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("""
                SELECT actor_short_name, turn, parsed_action
                FROM decisions
                WHERE doctrine_condition = ?
                AND final_applied = 1
                AND parsed_action IS NOT NULL
            """, (doctrine_condition,))
            for actor, turn, action_json in cur.fetchall():
                try:
                    action_dict = json.loads(action_json)
                    action_type = action_dict.get("action_type", "")
                    if action_type:
                        action_log[actor][turn].append(action_type)
                except Exception:
                    pass
            conn.close()

        if not action_log:
            return {"error": "No valid decisions found for this doctrine condition."}

        per_actor_bci: Dict[str, Dict] = {}

        for actor, turn_actions in action_log.items():
            turn_bcis_action = []
            turn_bcis_category = []
            action_totals: Dict[str, int] = defaultdict(int)
            category_totals: Dict[str, int] = defaultdict(int)

            for turn, actions in turn_actions.items():
                # Action-level distribution for this turn
                turn_counts: Dict[str, int] = defaultdict(int)
                cat_counts: Dict[str, int] = defaultdict(int)
                for a in actions:
                    turn_counts[a] += 1
                    cat = ACTION_CATEGORIES.get(a, "unknown")
                    cat_counts[cat] += 1
                    action_totals[a] += 1
                    category_totals[cat] += 1

                if len(actions) > 1:  # Need multiple runs to measure variance
                    turn_bcis_action.append(
                        _normalized_entropy(dict(turn_counts), N_ACTIONS)
                    )
                    turn_bcis_category.append(
                        _normalized_entropy(dict(cat_counts), N_CATEGORIES)
                    )

            per_actor_bci[actor] = {
                "bci_action": round(
                    sum(turn_bcis_action) / len(turn_bcis_action), 3
                ) if turn_bcis_action else None,
                "bci_category": round(
                    sum(turn_bcis_category) / len(turn_bcis_category), 3
                ) if turn_bcis_category else None,
                "most_common_actions": sorted(
                    action_totals.items(), key=lambda x: -x[1]
                )[:5],
                "category_distribution": {
                    k: round(v / sum(category_totals.values()), 3)
                    for k, v in category_totals.items()
                } if category_totals else {},
                "n_turns_observed": len(turn_actions),
                "n_runs": len(db_paths),
            }

        # Aggregate BCI across actors
        actor_action_bcis = [
            v["bci_action"] for v in per_actor_bci.values()
            if v["bci_action"] is not None
        ]
        actor_cat_bcis = [
            v["bci_category"] for v in per_actor_bci.values()
            if v["bci_category"] is not None
        ]

        return {
            "doctrine_condition": doctrine_condition,
            "n_runs": len(db_paths),
            "aggregate_bci_action": round(
                sum(actor_action_bcis) / len(actor_action_bcis), 3
            ) if actor_action_bcis else None,
            "aggregate_bci_category": round(
                sum(actor_cat_bcis) / len(actor_cat_bcis), 3
            ) if actor_cat_bcis else None,
            "per_actor": per_actor_bci,
        }

    def compare_conditions(
        self,
        condition_db_map: Dict[str, List[str]],
    ) -> Dict:
        """
        Compare BCI across multiple doctrine conditions.
        condition_db_map: {doctrine_condition: [db_path, ...]}
        """
        results = {}
        for condition, db_paths in condition_db_map.items():
            results[condition] = self.compute_from_db(db_paths, condition)

        # Summary table: condition -> aggregate BCI
        summary = {
            condition: {
                "bci_action": r.get("aggregate_bci_action"),
                "bci_category": r.get("aggregate_bci_category"),
                "n_runs": r.get("n_runs"),
            }
            for condition, r in results.items()
        }

        return {
            "summary": summary,
            "detail": results,
        }
