"""
Scenario template primitives for bounded open-ended crisis simulation.

This module defines the reusable state carried by the new scenario layer:
pressure snapshots, capability vectors, and a lightweight template runtime
that scenarios can subclass without changing the engine contract.

The runtime stays deterministic-given-seed and fully typed. It does not let
the model invent new world mechanics; it only turns state into bounded event
candidates and audit metadata.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from world.capabilities import CapabilityVector  # canonical — no local duplicate
from world.events import GlobalEvent
from world.state import WorldState


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _band(value: float) -> str:
    if value >= 0.66:
        return "HIGH"
    if value >= 0.33:
        return "MEDIUM"
    return "LOW"


class ScenarioPressureState(BaseModel):
    military_pressure: float = Field(ge=0.0, le=1.0)
    diplomatic_pressure: float = Field(ge=0.0, le=1.0)
    alliance_pressure: float = Field(ge=0.0, le=1.0)
    domestic_pressure: float = Field(ge=0.0, le=1.0)
    economic_pressure: float = Field(ge=0.0, le=1.0)
    information_pressure: float = Field(ge=0.0, le=1.0)
    crisis_instability: float = Field(ge=0.0, le=1.0)
    uncertainty: float = Field(ge=0.0, le=1.0)
    turn: int = 0
    previous_turn: Optional[int] = None
    drivers: Dict[str, float] = Field(default_factory=dict)
    notes: Dict[str, Any] = Field(default_factory=dict)

    def bands(self) -> Dict[str, str]:
        return {name: _band(getattr(self, name)) for name in (
            "military_pressure",
            "diplomatic_pressure",
            "alliance_pressure",
            "domestic_pressure",
            "economic_pressure",
            "information_pressure",
            "crisis_instability",
            "uncertainty",
        )}

    def blend(self, prior: Optional["ScenarioPressureState"], inertia: float) -> "ScenarioPressureState":
        if prior is None:
            return self

        values = {}
        for field_name in (
            "military_pressure",
            "diplomatic_pressure",
            "alliance_pressure",
            "domestic_pressure",
            "economic_pressure",
            "information_pressure",
            "crisis_instability",
            "uncertainty",
        ):
            current = getattr(self, field_name)
            previous = getattr(prior, field_name)
            values[field_name] = _clamp((current * (1.0 - inertia)) + (previous * inertia))

        return self.__class__(
            **values,
            turn=self.turn,
            previous_turn=prior.turn,
            drivers=self.drivers,
            notes=self.notes,
        )


class OpenEndedScenarioTemplate:
    """
    Reusable template helper for open-ended scenarios.

    Concrete scenarios are expected to implement:
      - build_initial_state()
      - build_event_templates()
      - build_pressure_coefficients()
    """

    def build_initial_state(self) -> WorldState:
        raise NotImplementedError

    def build_event_templates(self):
        raise NotImplementedError

    def build_pressure_coefficients(self) -> Dict[str, Dict[str, float]]:
        raise NotImplementedError

    def build_family_weights(self) -> Dict[str, float]:
        return {}

    def build_scenario_context(self, state: WorldState, pressures: ScenarioPressureState) -> Dict[str, Any]:
        return {}

    def max_events_per_turn(self) -> int:
        return 3

    def pressure_inertia(self) -> float:
        return 0.65

    def initialize(self) -> WorldState:
        state = self.build_initial_state()
        pressures = self.derive_pressures(state, turn=0, recent_context={})
        self._pressure_state = pressures
        self._pressure_history = [pressures]
        self._audit_history = []
        return state

    def get_turn_events(self, turn: int, state: WorldState) -> List[GlobalEvent]:
        from engine.event_generation import OpenEndedEventGenerator

        recent_context = self._recent_context(state)
        pressures = self.derive_pressures(state, turn=turn, recent_context=recent_context)
        capabilities = self.build_capability_profiles(state)
        scenario_context = self.build_scenario_context(state, pressures)
        scenario_context = {
            **scenario_context,
            "recent_context": recent_context,
            "state_signature": self.state_signature(state, pressures),
        }
        generator = OpenEndedEventGenerator(
            seed=getattr(self, "seed", 0),
            scenario_id=getattr(state, "scenario_id", "scenario"),
        )
        events, audit = generator.generate(
            turn=turn,
            state=state,
            pressures=pressures,
            capabilities=capabilities,
            event_templates=self.build_event_templates(),
            family_weights=self.build_family_weights(),
            scenario_context=scenario_context,
            recent_context=recent_context,
            max_events=self.max_events_per_turn(),
        )

        audit_event = GlobalEvent(
            turn=turn,
            category="injected",
            description=f"Open-ended scenario audit recorded for turn {turn}.",
            source="system",
            caused_by_actor=None,
            affected_actors=list(state.actors.keys()),
            world_state_delta={
                "pressure_snapshot": pressures.model_dump(),
                "pressure_bands": pressures.bands(),
                "capability_snapshot": {
                    actor_id: capability.model_dump()
                    for actor_id, capability in capabilities.items()
                },
                "audit": audit,
            },
        )

        self._pressure_state = pressures
        self._pressure_history.append(pressures)
        self._audit_history.append(audit)
        return [audit_event, *events]

    def derive_pressures(
        self,
        state: WorldState,
        turn: int,
        recent_context: Dict[str, Any],
    ) -> ScenarioPressureState:
        factors = self._pressure_factors(state, recent_context)
        coefficients = self.build_pressure_coefficients()
        outputs: Dict[str, float] = {}

        for output_name, mapping in coefficients.items():
            total_weight = sum(abs(weight) for weight in mapping.values()) or 1.0
            value = 0.0
            for factor_name, weight in mapping.items():
                value += factors.get(factor_name, 0.0) * weight
            outputs[output_name] = _clamp(value / total_weight)

        if "crisis_instability" not in outputs:
            outputs["crisis_instability"] = _clamp(
                0.40 * outputs.get("military_pressure", 0.0)
                + 0.15 * outputs.get("diplomatic_pressure", 0.0)
                + 0.15 * outputs.get("alliance_pressure", 0.0)
                + 0.15 * outputs.get("economic_pressure", 0.0)
                + 0.15 * outputs.get("uncertainty", 0.0)
            )

        if "uncertainty" not in outputs:
            outputs["uncertainty"] = _clamp(
                0.55 * factors.get("information_fog", 0.0)
                + 0.25 * factors.get("recent_ambiguity", 0.0)
                + 0.20 * factors.get("theater_pressure", 0.0)
            )

        pressures = ScenarioPressureState(
            military_pressure=outputs.get("military_pressure", 0.0),
            diplomatic_pressure=outputs.get("diplomatic_pressure", 0.0),
            alliance_pressure=outputs.get("alliance_pressure", 0.0),
            domestic_pressure=outputs.get("domestic_pressure", 0.0),
            economic_pressure=outputs.get("economic_pressure", 0.0),
            information_pressure=outputs.get("information_pressure", 0.0),
            crisis_instability=outputs.get("crisis_instability", 0.0),
            uncertainty=outputs.get("uncertainty", 0.0),
            turn=turn,
            previous_turn=getattr(getattr(self, "_pressure_state", None), "turn", None),
            drivers=factors,
            notes={
                "seed": getattr(self, "seed", 0),
                "scenario_id": state.scenario_id,
                "scenario_name": state.scenario_name,
            },
        )

        return pressures.blend(getattr(self, "_pressure_state", None), self.pressure_inertia())

    def build_capability_profiles(self, state: WorldState) -> Dict[str, CapabilityVector]:
        profiles: Dict[str, CapabilityVector] = {}

        for actor_id, actor in state.actors.items():
            alliance_strengths = [
                rel.alliance_strength
                for rel in state.relationships
                if rel.from_actor == actor_id and rel.relationship_type in ("ally", "partner")
            ]
            credibility_scores = [
                rel.deterrence_credibility
                for rel in state.relationships
                if rel.from_actor == actor_id
            ]
            theater_access = _clamp(
                0.40
                + (actor.territory.contested_zones.get("taiwan_strait", 0.0) * 0.35)
                + (max(actor.territory.strategic_straits.values(), default=0.0) * 0.25)
            )

            profiles[actor_id] = CapabilityVector(
                local_naval_projection=_clamp(actor.military.naval_power * theater_access),
                local_air_projection=_clamp(actor.military.air_superiority * theater_access),
                missile_a2ad_capability=_clamp(actor.military.a2ad_effectiveness),
                cyber_capability=_clamp(
                    (actor.economic.industrial_capacity * 0.45)
                    + (actor.information_quality * 0.35)
                    + (actor.political.decision_unity * 0.20)
                ),
                intelligence_quality=_clamp(actor.information_quality),
                economic_coercion_capacity=_clamp(
                    (actor.economic.gdp_strength * 0.40)
                    + (actor.economic.foreign_reserves * 0.30)
                    + (actor.economic.trade_openness * 0.30)
                ),
                alliance_leverage=_clamp(_mean(alliance_strengths)),
                logistics_endurance=_clamp(actor.military.logistics_capacity),
                domestic_stability=_clamp(actor.political.domestic_stability),
                war_aversion=_clamp(1.0 - actor.political.casualty_tolerance),
                escalation_tolerance=_clamp(actor.political.casualty_tolerance),
                bureaucratic_flexibility=_clamp(
                    (1.0 - actor.political.decision_unity) * 0.45
                    + actor.political.domestic_stability * 0.35
                    + actor.political.international_standing * 0.20
                ),
                signaling_credibility=_clamp(_mean(credibility_scores)),
                theater_access=theater_access,
            )

        return profiles

    def _recent_context(self, state: WorldState) -> Dict[str, Any]:
        if not state.turn_logs:
            return {
                "actions": {},
                "events": {},
                "descriptions": [],
                "event_occurrences": {},
                "event_last_turns": {},
            }

        last_log = state.turn_logs[-1]
        action_counts: Dict[str, int] = {}
        event_counts: Dict[str, int] = {}
        descriptions: List[str] = []
        event_occurrences: Dict[str, int] = {}
        event_last_turns: Dict[str, int] = {}

        for log in state.turn_logs:
            for event in getattr(log, "events_this_turn", []):
                generation = (event.world_state_delta or {}).get("generation", {})
                event_id = generation.get("event_id")
                if not event_id:
                    continue
                event_occurrences[event_id] = event_occurrences.get(event_id, 0) + 1
                event_last_turns[event_id] = int(log.turn)

        for decision in getattr(last_log, "decisions", []):
            action = getattr(decision, "parsed_action", None) or {}
            action_type = action.get("action_type")
            if action_type:
                action_counts[action_type] = action_counts.get(action_type, 0) + 1

        for event in list(getattr(last_log, "events_this_turn", [])) + list(getattr(last_log, "cascade_events", [])):
            event_counts[event.category] = event_counts.get(event.category, 0) + 1
            descriptions.append(event.description)

        return {
            "actions": action_counts,
            "events": event_counts,
            "descriptions": descriptions[-6:],
            "event_occurrences": event_occurrences,
            "event_last_turns": event_last_turns,
        }

    def _pressure_factors(self, state: WorldState, recent_context: Dict[str, Any]) -> Dict[str, float]:
        actors = list(state.actors.values())
        trust_scores = [
            rel.trust_score
            for rel in state.relationships
        ]
        threat_scores = [
            rel.threat_perception
            for rel in state.relationships
        ]
        readiness_scores = [actor.military.readiness for actor in actors]
        domestic_scores = [actor.political.domestic_stability for actor in actors]
        stability_scores = [actor.political.decision_unity for actor in actors]
        economic_scores = [actor.economic.gdp_strength for actor in actors]
        information_scores = [actor.information_quality for actor in actors]
        theater_controls = [
            actor.territory.contested_zones.get("taiwan_strait", 0.5)
            for actor in actors
        ]

        recent_actions = recent_context.get("actions", {})
        recent_events = recent_context.get("events", {})

        recent_military = _clamp(
            (
                recent_actions.get("strike", 0)
                + recent_actions.get("mobilize", 0)
                + recent_actions.get("advance", 0)
                + recent_actions.get("blockade", 0)
                + recent_actions.get("probe", 0)
                + recent_actions.get("signal_resolve", 0)
                + recent_events.get("military", 0)
            ) / max(1.0, len(actors) * 1.5)
        )
        recent_diplomatic = _clamp(
            (
                recent_actions.get("negotiate", 0)
                + recent_actions.get("back_channel", 0)
                + recent_actions.get("intel_sharing", 0)
                + recent_actions.get("form_alliance", 0)
                + recent_actions.get("condemn", 0)
                + recent_events.get("diplomatic", 0)
            ) / max(1.0, len(actors) * 1.5)
        )
        recent_economic = _clamp(
            (
                recent_actions.get("embargo", 0)
                + recent_actions.get("targeted_sanction", 0)
                + recent_actions.get("comprehensive_sanction", 0)
                + recent_actions.get("technology_restriction", 0)
                + recent_actions.get("foreign_aid", 0)
                + recent_events.get("economic", 0)
            ) / max(1.0, len(actors) * 1.5)
        )
        recent_information = _clamp(
            (
                recent_actions.get("propaganda", 0)
                + recent_actions.get("cyber_operation", 0)
                + recent_actions.get("partial_coercion", 0)
                + recent_events.get("information", 0)
            ) / max(1.0, len(actors))
        )
        recent_ambiguity = _clamp(
            sum(
                1 for description in recent_context.get("descriptions", [])
                if any(token in description.lower() for token in ("suspected", "uncertain", "contradict", "not yet confirmed", "attribution"))
            ) / max(1.0, len(recent_context.get("descriptions", [])) or 1)
        )

        military_heat = _clamp(
            (state.global_tension * 0.40)
            + ((1.0 - _mean(readiness_scores)) * 0.15)
            + (_mean(threat_scores) * 0.20)
            + (recent_military * 0.25)
        )
        diplomatic_fragmentation = _clamp(
            ((1.0 - _mean(trust_scores)) * 0.35)
            + (recent_diplomatic * 0.30)
            + ((1.0 - _mean(stability_scores)) * 0.15)
            + (state.global_tension * 0.20)
        )
        alliance_strain = _clamp(
            (1.0 - state.systemic.alliance_system_cohesion) * 0.45
            + (recent_military * 0.20)
            + (recent_diplomatic * 0.15)
            + (_mean(threat_scores) * 0.20)
        )
        domestic_fragility = _clamp(
            ((1.0 - _mean(domestic_scores)) * 0.45)
            + ((1.0 - _mean(stability_scores)) * 0.20)
            + (recent_military * 0.20)
            + (recent_information * 0.15)
        )
        economic_stress = _clamp(
            ((1.0 - _mean(economic_scores)) * 0.40)
            + (state.systemic.global_shipping_disruption * 0.20)
            + (state.systemic.energy_market_volatility * 0.20)
            + (recent_economic * 0.20)
        )
        information_fog = _clamp(
            ((1.0 - _mean(information_scores)) * 0.45)
            + (recent_information * 0.25)
            + (recent_ambiguity * 0.20)
            + (state.systemic.alliance_system_cohesion * 0.10)
        )
        theater_pressure = _clamp(1.0 - _mean(theater_controls))
        uncertainty_burst = _clamp(
            (information_fog * 0.55)
            + (recent_ambiguity * 0.25)
            + (state.systemic.global_shipping_disruption * 0.10)
            + ((1.0 - state.systemic.alliance_system_cohesion) * 0.10)
        )

        return {
            "global_tension": _clamp(state.global_tension),
            "military_heat": military_heat,
            "diplomatic_fragmentation": diplomatic_fragmentation,
            "alliance_strain": alliance_strain,
            "domestic_fragility": domestic_fragility,
            "economic_stress": economic_stress,
            "information_fog": information_fog,
            "recent_military": recent_military,
            "recent_diplomatic": recent_diplomatic,
            "recent_economic": recent_economic,
            "recent_information": recent_information,
            "recent_ambiguity": recent_ambiguity,
            "theater_pressure": theater_pressure,
            "uncertainty_burst": uncertainty_burst,
        }

    def state_signature(self, state: WorldState, pressures: ScenarioPressureState) -> str:
        payload = {
            "seed": getattr(self, "seed", 0),
            "scenario_id": state.scenario_id,
            "turn": state.turn,
            "crisis_phase": state.crisis_phase,
            "global_tension": round(state.global_tension, 4),
            "pressures": pressures.model_dump(),
            "actors": {
                name: {
                    "military": actor.military.model_dump(),
                    "economic": actor.economic.model_dump(),
                    "political": actor.political.model_dump(),
                    "territory": actor.territory.model_dump(),
                    "posture": actor.current_posture,
                }
                for name, actor in state.actors.items()
            },
            "relationships": [
                rel.model_dump()
                for rel in state.relationships
            ],
            "systemic": state.systemic.model_dump(),
            "recent_context": self._recent_context(state),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
