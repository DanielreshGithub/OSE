"""
Scenario pressure computation for OSE.

This module converts raw state, recent actions, and recent events into an
explicit pressure state that can drive event generation and perception.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from world.events import GlobalEvent
from world.pressures import PressureContribution, PressureState, empty_pressure_state
from world.state import WorldState


PHASE_RANK = {
    "peacetime": 0.05,
    "tension": 0.30,
    "crisis": 0.65,
    "war": 0.90,
    "post_conflict": 0.15,
}


ACTION_PRESSURE_MAP: Dict[str, Dict[str, float]] = {
    "mobilize": {"military_pressure": 0.08, "crisis_instability": 0.05},
    "strike": {"military_pressure": 0.16, "crisis_instability": 0.12, "alliance_pressure": 0.05},
    "advance": {"military_pressure": 0.10, "crisis_instability": 0.08},
    "withdraw": {"military_pressure": -0.05, "crisis_instability": -0.04},
    "blockade": {"military_pressure": 0.06, "economic_pressure": 0.10, "crisis_instability": 0.05},
    "defensive_posture": {"military_pressure": 0.02, "crisis_instability": 0.01},
    "probe": {"informational_pressure": 0.05, "uncertainty": -0.03},
    "signal_resolve": {"alliance_pressure": 0.04, "crisis_instability": 0.02},
    "deploy_forward": {"military_pressure": 0.09, "alliance_pressure": 0.03, "crisis_instability": 0.05},
    "negotiate": {"diplomatic_pressure": -0.06, "crisis_instability": -0.04},
    "targeted_sanction": {"economic_pressure": 0.07, "diplomatic_pressure": 0.03},
    "comprehensive_sanction": {"economic_pressure": 0.12, "diplomatic_pressure": 0.04, "crisis_instability": 0.03},
    "form_alliance": {"alliance_pressure": 0.06, "diplomatic_pressure": 0.02},
    "condemn": {"diplomatic_pressure": 0.02, "informational_pressure": 0.02},
    "intel_sharing": {"informational_pressure": -0.04, "uncertainty": -0.05, "alliance_pressure": -0.02},
    "back_channel": {"diplomatic_pressure": -0.05, "uncertainty": -0.03},
    "lawfare_filing": {"diplomatic_pressure": 0.03, "informational_pressure": 0.02, "crisis_instability": -0.01},
    "multilateral_appeal": {"diplomatic_pressure": -0.05, "alliance_pressure": -0.03, "uncertainty": -0.02},
    "expel_diplomats": {"diplomatic_pressure": 0.07, "crisis_instability": 0.03, "uncertainty": 0.02},
    "embargo": {"economic_pressure": 0.10, "crisis_instability": 0.03},
    "foreign_aid": {"alliance_pressure": -0.03, "economic_pressure": -0.02},
    "cut_supply": {"economic_pressure": 0.08, "informational_pressure": 0.02},
    "technology_restriction": {"economic_pressure": 0.08, "informational_pressure": 0.03},
    "asset_freeze": {"economic_pressure": 0.09, "diplomatic_pressure": 0.03},
    "supply_chain_diversion": {"economic_pressure": -0.03, "alliance_pressure": -0.01},
    "propaganda": {"informational_pressure": 0.07, "domestic_pressure": 0.02},
    "partial_coercion": {"military_pressure": 0.05, "domestic_pressure": 0.03, "crisis_instability": 0.04},
    "cyber_operation": {"informational_pressure": 0.08, "uncertainty": 0.08},
    "hack_and_leak": {"informational_pressure": 0.10, "uncertainty": 0.07, "domestic_pressure": 0.04},
    "nuclear_signal": {"military_pressure": 0.12, "crisis_instability": 0.16, "alliance_pressure": 0.05},
    "hold_position": {"crisis_instability": -0.01},
    "monitor": {"uncertainty": -0.02},
}


EVENT_PRESSURE_MAP: Dict[str, Dict[str, float]] = {
    "military": {"military_pressure": 0.05, "crisis_instability": 0.04},
    "diplomatic": {"diplomatic_pressure": 0.03},
    "economic": {"economic_pressure": 0.05},
    "information": {"informational_pressure": 0.05, "uncertainty": 0.03},
    "natural": {"domestic_pressure": 0.03, "crisis_instability": -0.01},
    "cascade": {"crisis_instability": 0.03},
    "injected": {"crisis_instability": 0.02},
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _average(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        return 0.0
    return sum(values) / len(values)


def _contradictory_signal_count(events: Iterable[GlobalEvent]) -> int:
    markers = ("suspected", "unconfirmed", "contradict", "unclear", "ambiguous")
    total = 0
    for event in events:
        lowered = event.description.lower()
        if any(marker in lowered for marker in markers):
            total += 1
    return total


def _action_records(turn_actions: Optional[Dict[str, Tuple[Any, Any]]], state: WorldState) -> List[Tuple[str, str]]:
    if turn_actions:
        return [(actor_id, action.action_type) for actor_id, (action, _) in turn_actions.items()]
    if not state.turn_logs:
        return []
    last_log = state.turn_logs[-1]
    rows: List[Tuple[str, str]] = []
    for record in getattr(last_log, "decisions", []):
        parsed = record.parsed_action or {}
        action_type = parsed.get("action_type")
        if action_type:
            rows.append((record.actor_short_name, action_type))
    return rows


class ScenarioPressureModel:
    """
    Deterministic pressure model driven by explicit state and recent history.
    """

    def __init__(self, scenario_id: str, smoothing: float = 0.40, pressure_weights: Optional[Dict[str, float]] = None):
        self.scenario_id = scenario_id
        self.smoothing = smoothing
        self.pressure_weights = pressure_weights or {}

    def compute(
        self,
        state: WorldState,
        turn_actions: Optional[Dict[str, Tuple[Any, Any]]] = None,
        recent_events: Optional[List[GlobalEvent]] = None,
        previous: Optional[PressureState] = None,
    ) -> PressureState:
        previous = previous or getattr(state, "pressures", None) or empty_pressure_state(
            turn=state.turn,
            scenario_id=state.scenario_id,
        )
        recent_events = recent_events or []
        action_rows = _action_records(turn_actions, state)

        avg_readiness = _average(actor.military.readiness for actor in state.actors.values())
        avg_domestic = _average(actor.political.domestic_stability for actor in state.actors.values())
        avg_information = _average(actor.information_quality for actor in state.actors.values())
        avg_alliance = _average(rel.alliance_strength for rel in state.relationships)
        avg_trade = _average(actor.economic.trade_openness for actor in state.actors.values())

        baseline = {
            "military_pressure": _clamp(
                0.45 * state.global_tension
                + 0.20 * avg_readiness
                + 0.20 * PHASE_RANK.get(state.crisis_phase, 0.2)
                + 0.15 * len(state.active_conflicts)
            ),
            "diplomatic_pressure": _clamp(
                0.30 * state.global_tension
                + 0.20 * (1.0 - avg_alliance)
                + 0.20 * PHASE_RANK.get(state.crisis_phase, 0.2)
                + 0.15 * avg_trade
            ),
            "alliance_pressure": _clamp(
                0.35 * (1.0 - state.systemic.alliance_system_cohesion)
                + 0.30 * state.global_tension
                + 0.20 * avg_alliance
            ),
            "domestic_pressure": _clamp(
                0.40 * (1.0 - avg_domestic)
                + 0.20 * state.systemic.global_shipping_disruption
                + 0.20 * state.systemic.energy_market_volatility
            ),
            "economic_pressure": _clamp(
                0.30 * state.systemic.global_shipping_disruption
                + 0.30 * (1.0 - state.systemic.semiconductor_supply_chain_integrity)
                + 0.20 * avg_trade
                + 0.20 * state.systemic.energy_market_volatility
            ),
            "informational_pressure": _clamp(
                0.25 * state.global_tension
                + 0.25 * (1.0 - avg_information)
                + 0.15 * PHASE_RANK.get(state.crisis_phase, 0.2)
            ),
            "crisis_instability": _clamp(
                0.50 * state.global_tension
                + 0.30 * PHASE_RANK.get(state.crisis_phase, 0.2)
                + 0.20 * len(state.active_conflicts)
            ),
            "uncertainty": _clamp(
                0.45 * (1.0 - avg_information)
                + 0.20 * state.systemic.global_shipping_disruption
                + 0.10 * PHASE_RANK.get(state.crisis_phase, 0.2)
            ),
        }

        contributions: List[PressureContribution] = []
        dynamic = {name: 0.0 for name in baseline}

        for actor_id, action_type in action_rows:
            deltas = ACTION_PRESSURE_MAP.get(action_type, {})
            for dimension, delta in deltas.items():
                dynamic[dimension] += delta
                contributions.append(PressureContribution(
                    dimension=dimension,
                    delta=delta,
                    source="action",
                    reason=f"Action '{action_type}' by {actor_id}",
                    actor_short_name=actor_id,
                    turn=state.turn,
                    metadata={"action_type": action_type},
                ))

        contradictory_count = _contradictory_signal_count(recent_events)
        if contradictory_count:
            bump = 0.03 * contradictory_count
            dynamic["uncertainty"] += bump
            dynamic["informational_pressure"] += bump * 0.7
            contributions.append(PressureContribution(
                dimension="uncertainty",
                delta=bump,
                source="event",
                reason="Contradictory or ambiguous signals increased uncertainty",
                turn=state.turn,
                metadata={"contradictory_signal_count": contradictory_count},
            ))

        for event in recent_events:
            deltas = EVENT_PRESSURE_MAP.get(event.category, {})
            direction = float(event.world_state_delta.get("global_tension_delta", 0.0))
            if event.category == "diplomatic" and direction < 0:
                deltas = {
                    **deltas,
                    "diplomatic_pressure": deltas.get("diplomatic_pressure", 0.0) - 0.05,
                    "crisis_instability": -0.03,
                }
            for dimension, delta in deltas.items():
                dynamic[dimension] += delta
                contributions.append(PressureContribution(
                    dimension=dimension,
                    delta=delta,
                    source="event" if event.source != "cascade" else "cascade",
                    reason=event.description,
                    actor_short_name=event.caused_by_actor,
                    turn=event.turn,
                    metadata={
                        "category": event.category,
                        "source": event.source,
                        "event_family": event.event_family,
                    },
                ))

        values: Dict[str, float] = {}
        for dimension, baseline_value in baseline.items():
            weighted = _clamp(baseline_value + dynamic[dimension] * self.pressure_weights.get(dimension, 1.0))
            previous_value = float(getattr(previous, dimension, 0.0))
            values[dimension] = _clamp(
                (1.0 - self.smoothing) * previous_value + self.smoothing * weighted
            )

        pressure_state = PressureState(
            military_pressure=values["military_pressure"],
            diplomatic_pressure=values["diplomatic_pressure"],
            alliance_pressure=values["alliance_pressure"],
            domestic_pressure=values["domestic_pressure"],
            economic_pressure=values["economic_pressure"],
            informational_pressure=values["informational_pressure"],
            crisis_instability=values["crisis_instability"],
            uncertainty=values["uncertainty"],
            turn=state.turn,
            scenario_id=self.scenario_id,
            last_updated=datetime.utcnow(),
            contributions=contributions,
            metadata={
                "baseline": {k: round(v, 4) for k, v in baseline.items()},
                "dynamic": {k: round(v, 4) for k, v in dynamic.items()},
                "recent_action_count": len(action_rows),
                "recent_event_count": len(recent_events),
                "contradictory_signal_count": contradictory_count,
            },
        )
        return pressure_state.clamp()
