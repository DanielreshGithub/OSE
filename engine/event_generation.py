"""
Deterministic open-ended event generation for OSE.

This layer turns scenario pressures, recent context, and actor capabilities
into typed event candidates. It does not invent world mechanics or free-text
outcomes; it only ranks bounded templates and samples from them with a seeded
RNG.
"""
from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, Field

from world.capabilities import CapabilityVector
from engine.scenario_template import ScenarioPressureState
from world.events import GlobalEvent
from world.state import WorldState


class PressureGate(BaseModel):
    pressure: str
    min_value: float = 0.0
    max_value: float = 1.0
    weight: float = 1.0


class CapabilityGate(BaseModel):
    actor: str
    capability: str
    min_value: float = 0.0
    weight: float = 1.0


class EventTemplate(BaseModel):
    event_id: str
    family: str
    category: str
    description: str
    source: str = "injected"
    caused_by_actor: Optional[str] = None
    affected_actors: List[str] = Field(default_factory=list)
    base_weight: float = 1.0
    pressure_gates: List[PressureGate] = Field(default_factory=list)
    capability_gates: List[CapabilityGate] = Field(default_factory=list)
    phase_bias: List[str] = Field(default_factory=list)
    recent_action_bias: Dict[str, float] = Field(default_factory=dict)
    min_turn: Optional[int] = None
    max_turn: Optional[int] = None
    one_shot: bool = False
    cooldown_turns: int = 0
    world_state_delta: Dict[str, Any] = Field(default_factory=dict)
    tags: List[str] = Field(default_factory=list)


class EventCandidate(BaseModel):
    template: EventTemplate
    eligible: bool = True
    score: float = 0.0
    base_weight: float = 0.0
    pressure_score: float = 0.0
    capability_score: float = 0.0
    phase_score: float = 0.0
    action_score: float = 0.0
    family_score: float = 0.0
    reasons: List[str] = Field(default_factory=list)
    weight_breakdown: Dict[str, float] = Field(default_factory=dict)

    def audit_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.template.event_id,
            "family": self.template.family,
            "category": self.template.category,
            "score": round(self.score, 4),
            "reasons": self.reasons,
            "weight_breakdown": self.weight_breakdown,
        }


class EventEligibilityEvaluator:
    def evaluate(
        self,
        *,
        turn: int,
        state: WorldState,
        pressures: ScenarioPressureState,
        capabilities: Dict[str, CapabilityVector],
        event_templates: Sequence[EventTemplate],
        family_weights: Dict[str, float],
        recent_context: Dict[str, Any],
        scenario_context: Dict[str, Any],
    ) -> Tuple[List[EventCandidate], Dict[str, Any]]:
        candidates: List[EventCandidate] = []
        rejected: List[Dict[str, Any]] = []

        for template in event_templates:
            candidate = self._evaluate_template(
                turn=turn,
                state=state,
                pressures=pressures,
                capabilities=capabilities,
                template=template,
                family_weights=family_weights,
                recent_context=recent_context,
                scenario_context=scenario_context,
            )
            if candidate.eligible:
                candidates.append(candidate)
            else:
                rejected.append(candidate.audit_dict())

        candidates.sort(key=lambda c: c.score, reverse=True)
        audit = {
            "turn": turn,
            "evaluated_templates": len(event_templates),
            "eligible_candidates": [c.audit_dict() for c in candidates],
            "rejected_candidates": rejected,
            "pressure_bands": pressures.bands(),
            "pressure_snapshot": pressures.model_dump(),
            "recent_context": recent_context,
            "scenario_context": scenario_context,
        }
        return candidates, audit

    def _evaluate_template(
        self,
        *,
        turn: int,
        state: WorldState,
        pressures: ScenarioPressureState,
        capabilities: Dict[str, CapabilityVector],
        template: EventTemplate,
        family_weights: Dict[str, float],
        recent_context: Dict[str, Any],
        scenario_context: Dict[str, Any],
    ) -> EventCandidate:
        reasons: List[str] = []
        weight_breakdown: Dict[str, float] = {}
        eligible = True

        if template.min_turn is not None and turn < template.min_turn:
            return EventCandidate(
                template=template,
                eligible=False,
                reasons=[f"turn<{template.min_turn}"],
            )
        if template.max_turn is not None and turn > template.max_turn:
            return EventCandidate(
                template=template,
                eligible=False,
                reasons=[f"turn>{template.max_turn}"],
            )

        event_occurrences = recent_context.get("event_occurrences", {})
        event_last_turns = recent_context.get("event_last_turns", {})
        if template.one_shot and int(event_occurrences.get(template.event_id, 0)) > 0:
            return EventCandidate(
                template=template,
                eligible=False,
                reasons=[f"one_shot_already_triggered:{template.event_id}"],
            )
        last_turn = event_last_turns.get(template.event_id)
        if (
            template.cooldown_turns > 0
            and last_turn is not None
            and (turn - int(last_turn)) <= template.cooldown_turns
        ):
            return EventCandidate(
                template=template,
                eligible=False,
                reasons=[
                    f"cooldown_active:{template.event_id} last_turn={last_turn} cooldown={template.cooldown_turns}"
                ],
            )

        base_weight = max(template.base_weight, 0.0)
        family_score = family_weights.get(template.family, 1.0)
        weight_breakdown["base_weight"] = base_weight
        weight_breakdown["family_weight"] = family_score

        pressure_score = 1.0
        for gate in template.pressure_gates:
            value = getattr(pressures, gate.pressure, None)
            if value is None:
                return EventCandidate(
                    template=template,
                    eligible=False,
                    reasons=[f"missing_pressure:{gate.pressure}"],
                )
            if value < gate.min_value or value > gate.max_value:
                return EventCandidate(
                    template=template,
                    eligible=False,
                    reasons=[
                        f"pressure_gate_failed:{gate.pressure}={value:.2f} "
                        f"not in [{gate.min_value:.2f}, {gate.max_value:.2f}]"
                    ],
                )

            if gate.max_value <= gate.min_value:
                normalized = 1.0
            else:
                normalized = (value - gate.min_value) / (gate.max_value - gate.min_value)
            contribution = 1.0 + (normalized * gate.weight)
            pressure_score *= contribution
            reasons.append(
                f"{gate.pressure}={value:.2f} within [{gate.min_value:.2f}, {gate.max_value:.2f}]"
            )

        capability_score = 1.0
        for gate in template.capability_gates:
            actor_caps = capabilities.get(gate.actor)
            if actor_caps is None:
                return EventCandidate(
                    template=template,
                    eligible=False,
                    reasons=[f"missing_capability_actor:{gate.actor}"],
                )
            value = getattr(actor_caps, gate.capability, None)
            if value is None:
                return EventCandidate(
                    template=template,
                    eligible=False,
                    reasons=[f"missing_capability:{gate.actor}.{gate.capability}"],
                )
            if value < gate.min_value:
                return EventCandidate(
                    template=template,
                    eligible=False,
                    reasons=[
                        f"capability_gate_failed:{gate.actor}.{gate.capability}={value:.2f} "
                        f"< {gate.min_value:.2f}"
                    ],
                )
            capability_score *= 1.0 + ((value - gate.min_value) * gate.weight)
            reasons.append(
                f"{gate.actor}.{gate.capability}={value:.2f}>= {gate.min_value:.2f}"
            )

        phase_score = 1.0
        if template.phase_bias:
            if state.crisis_phase in template.phase_bias:
                phase_score = 1.15
                reasons.append(f"phase_bias:{state.crisis_phase}")
            else:
                phase_score = 0.55
                reasons.append(f"phase_off_bias:{state.crisis_phase}")

        action_score = 1.0
        recent_actions = recent_context.get("actions", {})
        for action_type, multiplier in template.recent_action_bias.items():
            if recent_actions.get(action_type, 0) > 0:
                action_score += multiplier
                reasons.append(f"recent_action:{action_type}")

        if "scenario_bias" in scenario_context:
            action_score += float(scenario_context.get("scenario_bias", 0.0))

        score = (
            base_weight
            * family_score
            * pressure_score
            * capability_score
            * phase_score
            * action_score
        )

        if score <= 0.0:
            eligible = False
            reasons.append("non_positive_score")

        return EventCandidate(
            template=template,
            eligible=eligible,
            score=score,
            base_weight=base_weight,
            pressure_score=pressure_score,
            capability_score=capability_score,
            phase_score=phase_score,
            action_score=action_score,
            family_score=family_score,
            reasons=reasons,
            weight_breakdown=weight_breakdown,
        )


class EventSampler:
    def sample(
        self,
        candidates: Sequence[EventCandidate],
        rng: random.Random,
        budget: int,
    ) -> List[EventCandidate]:
        remaining = [candidate for candidate in candidates if candidate.eligible and candidate.score > 0.0]
        if not remaining or budget <= 0:
            return []

        selected: List[EventCandidate] = []
        while remaining and len(selected) < budget:
            weights = [max(candidate.score, 0.001) for candidate in remaining]
            index = rng.choices(range(len(remaining)), weights=weights, k=1)[0]
            selected.append(remaining.pop(index))

        return sorted(selected, key=lambda candidate: candidate.score, reverse=True)


class OpenEndedEventGenerator:
    def __init__(self, seed: int, scenario_id: str):
        self.seed = int(seed)
        self.scenario_id = scenario_id
        self._evaluator = EventEligibilityEvaluator()
        self._sampler = EventSampler()

    def generate(
        self,
        *,
        turn: int,
        state: WorldState,
        pressures: ScenarioPressureState,
        capabilities: Dict[str, CapabilityVector],
        event_templates: Sequence[EventTemplate],
        family_weights: Dict[str, float],
        scenario_context: Dict[str, Any],
        recent_context: Dict[str, Any],
        max_events: int,
    ) -> Tuple[List[GlobalEvent], Dict[str, Any]]:
        candidates, audit = self._evaluator.evaluate(
            turn=turn,
            state=state,
            pressures=pressures,
            capabilities=capabilities,
            event_templates=event_templates,
            family_weights=family_weights,
            recent_context=recent_context,
            scenario_context=scenario_context,
        )

        budget = self._event_budget(pressures, max_events, scenario_context)
        rng = random.Random(self._seed_for_turn(state, pressures, turn, scenario_context))
        selected = self._sampler.sample(candidates, rng, budget)

        events = [
            self._instantiate_event(
                state=state,
                pressures=pressures,
                capabilities=capabilities,
                candidate=candidate,
                turn=turn,
                rank=index,
                recent_context=recent_context,
                scenario_context=scenario_context,
            )
            for index, candidate in enumerate(selected, start=1)
        ]

        audit.update(
            {
                "budget": budget,
                "selected_candidates": [candidate.audit_dict() for candidate in selected],
                "selected_event_ids": [candidate.template.event_id for candidate in selected],
                "state_signature": scenario_context.get("state_signature") or self._state_signature(
                    state=state,
                    pressures=pressures,
                    recent_context=recent_context,
                ),
                "seed": self.seed,
            }
        )

        return events, audit

    def _event_budget(
        self,
        pressures: ScenarioPressureState,
        max_events: int,
        scenario_context: Dict[str, Any],
    ) -> int:
        budget = int(scenario_context.get("base_event_budget", 1))
        if pressures.crisis_instability >= 0.45:
            budget += 1
        if pressures.crisis_instability >= 0.70 or pressures.uncertainty >= 0.60 or pressures.economic_pressure >= 0.65:
            budget += 1
        return max(1, min(max_events, budget))

    def _seed_for_turn(
        self,
        state: WorldState,
        pressures: ScenarioPressureState,
        turn: int,
        scenario_context: Dict[str, Any],
    ) -> int:
        payload = {
            "seed": self.seed,
            "scenario_id": self.scenario_id,
            "turn": turn,
            "state_signature": scenario_context.get("state_signature") or self._state_signature(
                state=state,
                pressures=pressures,
                recent_context=scenario_context.get("recent_context", {}),
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return int(hashlib.sha256(encoded).hexdigest()[:16], 16)

    def _state_signature(
        self,
        *,
        state: WorldState,
        pressures: ScenarioPressureState,
        recent_context: Dict[str, Any],
    ) -> str:
        payload = {
            "seed": self.seed,
            "scenario_id": self.scenario_id,
            "turn": state.turn,
            "crisis_phase": state.crisis_phase,
            "global_tension": round(state.global_tension, 4),
            "pressures": pressures.model_dump(),
            "recent_context": recent_context,
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
            "relationships": [rel.model_dump() for rel in state.relationships],
            "systemic": state.systemic.model_dump(),
        }
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _instantiate_event(
        self,
        *,
        state: WorldState,
        pressures: ScenarioPressureState,
        capabilities: Dict[str, CapabilityVector],
        candidate: EventCandidate,
        turn: int,
        rank: int,
        recent_context: Dict[str, Any],
        scenario_context: Dict[str, Any],
    ) -> GlobalEvent:
        template = candidate.template
        delta = dict(template.world_state_delta)
        delta["generation"] = {
            "event_id": template.event_id,
            "family": template.family,
            "score": round(candidate.score, 4),
            "rank": rank,
            "reasons": candidate.reasons,
            "weight_breakdown": candidate.weight_breakdown,
            "pressure_snapshot": pressures.model_dump(),
            "pressure_bands": pressures.bands(),
            "capability_snapshot": {
                actor_id: capability.bands()
                for actor_id, capability in capabilities.items()
            },
            "recent_context": recent_context,
            "state_signature": scenario_context.get("state_signature") or self._state_signature(
                state=state,
                pressures=pressures,
                recent_context=recent_context,
            ),
        }
        return GlobalEvent(
            turn=turn,
            category=template.category,
            description=template.description,
            source=template.source,
            caused_by_actor=template.caused_by_actor,
            affected_actors=list(template.affected_actors),
            world_state_delta=delta,
        )
