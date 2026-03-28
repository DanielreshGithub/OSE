"""
CascadeDetector — structural downstream effects after turn resolution.

Cascades are narrow, mechanical rules — not narrative generation.
Each rule checks a specific condition in the post-resolution world state
and applies a downstream effect if triggered.

This is where systemic emergence lives: PRC mobilizes → JPN threat perception
rises → JPN adopts defensive posture next turn. The LLM actor sees these
cascade events as part of the next turn's context, which shapes its reasoning.

Rules applied in order (some may chain):
  1. Crisis phase transition (tension thresholds)
  2. Strike cascade — allies of struck actor raise readiness
  3. Mobilization cascade — adversaries raise threat perception
  4. Blockade/embargo cascade — semiconductor supply chain degrades
  5. Alliance commitment test — cohesion degrades if ally struck and helper stays idle
  6. Economic pressure cascade — GDP collapse triggers political instability
  7. Diplomatic de-escalation — negotiate reduces bilateral threat perception + tension
  8. Back-channel cascade — quiet diplomacy reduces threat perception
  9. Aid & alliance cascade — foreign_aid stabilizes recipient; intel_sharing builds trust;
     form_alliance strengthens systemic cohesion

Cooperative cascades are intentionally weaker than escalatory ones — de-escalation
is structurally harder than escalation. Mutual negotiation (both sides same turn)
triggers a larger effect than unilateral negotiation.
"""
from __future__ import annotations

from typing import Dict, List, Tuple, Any

from world.state import WorldState
from world.events import GlobalEvent
from engine.actions import (
    BaseAction, StrikeAction, MobilizeAction, BlockadeAction, EmbargoAction,
    NegotiateAction, BackChannelAction, ForeignAidAction, IntelSharingAction, FormAllianceAction,
)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


# Crisis phase thresholds (global_tension -> phase)
PHASE_THRESHOLDS = [
    (0.85, "war"),
    (0.65, "crisis"),
    (0.40, "tension"),
    (0.00, "peacetime"),
]

# De-escalation is slower — require tension to drop significantly before stepping down
PHASE_DEESCALATE_THRESHOLDS = {
    "war": 0.70,       # must drop below 0.70 to leave war
    "crisis": 0.45,    # must drop below 0.45 to leave crisis
    "tension": 0.25,   # must drop below 0.25 to return to peacetime
}


class CascadeDetector:
    """
    Applies downstream cascade effects after turn resolution.
    Returns (mutated_state, cascade_events).
    """

    def detect(
        self,
        state: WorldState,
        turn_actions: Dict[str, Tuple[BaseAction, Any]],
    ) -> Tuple[WorldState, List[GlobalEvent]]:
        """
        Detect and apply all cascade effects for this turn.
        turn_actions: {actor_id: (action, decision_record)}
        """
        cascades: List[GlobalEvent] = []
        actions = {name: act for name, (act, _) in turn_actions.items()}

        cascades += self._crisis_phase_transition(state)
        cascades += self._strike_cascade(state, actions)
        cascades += self._mobilization_cascade(state, actions)
        cascades += self._supply_chain_cascade(state, actions)
        cascades += self._alliance_cohesion_cascade(state, actions)
        cascades += self._economic_collapse_cascade(state)
        cascades += self._diplomatic_deescalation_cascade(state, actions)
        cascades += self._back_channel_cascade(state, actions)
        cascades += self._aid_and_alliance_cascade(state, actions)

        state.clamp_all_resources()
        return state, cascades

    # ── Rule 1: Crisis phase transition ───────────────────────────────────────

    def _crisis_phase_transition(self, state: WorldState) -> List[GlobalEvent]:
        events = []
        tension = state.global_tension
        current = state.crisis_phase

        # Escalation: move up if tension crosses threshold
        new_phase = current
        for threshold, phase in PHASE_THRESHOLDS:
            if tension >= threshold:
                new_phase = phase
                break

        # De-escalation: only step down if tension drops sufficiently
        if current == "war" and tension < PHASE_DEESCALATE_THRESHOLDS["war"]:
            new_phase = "crisis"
        elif current == "crisis" and tension < PHASE_DEESCALATE_THRESHOLDS["crisis"]:
            new_phase = "tension"
        elif current == "tension" and tension < PHASE_DEESCALATE_THRESHOLDS["tension"]:
            new_phase = "peacetime"

        if new_phase != current:
            state.crisis_phase = new_phase
            direction = "escalates" if _phase_rank(new_phase) > _phase_rank(current) else "de-escalates"
            events.append(GlobalEvent(
                turn=state.turn, category="cascade",
                description=(
                    f"[CASCADE] Crisis phase {direction}: "
                    f"{current} → {new_phase} (tension={tension:.2f})"
                ),
                source="cascade",
                affected_actors=list(state.actors.keys()),
                world_state_delta={"crisis_phase": f"{current} → {new_phase}"},
            ))

        return events

    # ── Rule 2: Strike cascade — allies of target raise readiness ─────────────

    def _strike_cascade(
        self, state: WorldState, actions: Dict[str, BaseAction]
    ) -> List[GlobalEvent]:
        events = []
        for actor_id, action in actions.items():
            if not isinstance(action, StrikeAction) or not action.target_actor:
                continue
            target_id = action.target_actor
            # Find allies of the struck actor
            allies_of_target = state.get_allies(target_id, min_strength=0.3)
            for ally_id in allies_of_target:
                if ally_id == actor_id:
                    continue
                ally = state.get_actor(ally_id)
                if ally is None:
                    continue
                readiness_gain = 0.10
                ally.military.readiness = _clamp(ally.military.readiness + readiness_gain)
                # Update threat perception toward the striker
                rel = state.get_relationship(ally_id, actor_id)
                if rel:
                    rel.threat_perception = _clamp(rel.threat_perception + 0.08)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] {actor_id} struck {target_id} → "
                        f"{ally_id} (ally) raises readiness +{readiness_gain:.2f}, "
                        f"threat perception of {actor_id} increases."
                    ),
                    source="cascade",
                    caused_by_actor=actor_id,
                    affected_actors=[ally_id],
                    world_state_delta={
                        f"{ally_id}.military.readiness": f"+{readiness_gain:.2f}",
                        f"{ally_id}→{actor_id}.threat_perception": "+0.08",
                    },
                ))
        return events

    # ── Rule 3: Mobilization cascade — adversaries raise threat perception ─────

    def _mobilization_cascade(
        self, state: WorldState, actions: Dict[str, BaseAction]
    ) -> List[GlobalEvent]:
        events = []
        for actor_id, action in actions.items():
            if not isinstance(action, MobilizeAction):
                continue
            adversaries = state.get_adversaries(actor_id)
            for adv_id in adversaries:
                adv = state.get_actor(adv_id)
                if adv is None:
                    continue
                rel = state.get_relationship(adv_id, actor_id)
                if rel:
                    old_tp = rel.threat_perception
                    rel.threat_perception = _clamp(rel.threat_perception + 0.07)
                    events.append(GlobalEvent(
                        turn=state.turn, category="cascade",
                        description=(
                            f"[CASCADE] {actor_id} mobilizes → "
                            f"{adv_id} raises threat perception of {actor_id} "
                            f"({old_tp:.2f} → {rel.threat_perception:.2f})."
                        ),
                        source="cascade",
                        caused_by_actor=actor_id,
                        affected_actors=[adv_id],
                        world_state_delta={
                            f"{adv_id}→{actor_id}.threat_perception": "+0.07",
                        },
                    ))
        return events

    # ── Rule 4: Supply chain cascade ──────────────────────────────────────────

    def _supply_chain_cascade(
        self, state: WorldState, actions: Dict[str, BaseAction]
    ) -> List[GlobalEvent]:
        events = []
        blockade_count = sum(1 for a in actions.values() if isinstance(a, BlockadeAction))
        embargo_count = sum(1 for a in actions.values() if isinstance(a, EmbargoAction))

        # Taiwan Strait disruption: any blockade or embargo degrades semiconductor supply
        if blockade_count > 0 or embargo_count > 0:
            degradation = (blockade_count * 0.06) + (embargo_count * 0.03)
            old = state.systemic.semiconductor_supply_chain_integrity
            state.systemic.semiconductor_supply_chain_integrity = _clamp(old - degradation)
            events.append(GlobalEvent(
                turn=state.turn, category="cascade",
                description=(
                    f"[CASCADE] Economic coercion ({blockade_count} blockade(s), "
                    f"{embargo_count} embargo(s)) → semiconductor supply chain "
                    f"integrity degrades ({old:.2f} → "
                    f"{state.systemic.semiconductor_supply_chain_integrity:.2f})."
                ),
                source="cascade",
                affected_actors=list(state.actors.keys()),
                world_state_delta={
                    "systemic.semiconductor_supply_chain_integrity":
                        f"{old:.2f} → {state.systemic.semiconductor_supply_chain_integrity:.2f}"
                },
            ))
        return events

    # ── Rule 5: Alliance cohesion cascade ─────────────────────────────────────

    def _alliance_cohesion_cascade(
        self, state: WorldState, actions: Dict[str, BaseAction]
    ) -> List[GlobalEvent]:
        """
        If an actor is struck and none of its allies take an active response
        (strike, mobilize, signal_resolve, sanction), alliance cohesion degrades.
        """
        events = []
        from engine.actions import (
            SignalResolveAction, TargetedSanctionAction, ComprehensiveSanctionAction
        )

        for actor_id, action in actions.items():
            if not isinstance(action, StrikeAction) or not action.target_actor:
                continue
            target_id = action.target_actor
            allies = state.get_allies(target_id, min_strength=0.4)
            if not allies:
                continue

            active_responses = {
                a for a, act in actions.items()
                if a in allies and isinstance(
                    act, (StrikeAction, MobilizeAction, SignalResolveAction,
                          TargetedSanctionAction, ComprehensiveSanctionAction)
                )
            }

            if not active_responses and len(allies) > 0:
                # No ally responded — credibility hit
                degradation = 0.05
                old = state.systemic.alliance_system_cohesion
                state.systemic.alliance_system_cohesion = _clamp(old - degradation)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] {target_id} struck by {actor_id}; "
                        f"allies {allies} did not respond → "
                        f"alliance system cohesion degrades "
                        f"({old:.2f} → {state.systemic.alliance_system_cohesion:.2f})."
                    ),
                    source="cascade",
                    affected_actors=allies + [target_id],
                    world_state_delta={
                        "systemic.alliance_system_cohesion":
                            f"{old:.2f} → {state.systemic.alliance_system_cohesion:.2f}"
                    },
                ))
        return events

    # ── Rule 6: Economic collapse cascade ────────────────────────────────────

    def _economic_collapse_cascade(self, state: WorldState) -> List[GlobalEvent]:
        """
        If any actor's GDP falls below 0.25, their domestic stability degrades.
        Models the political cost of economic collapse under sanctions/embargo.
        """
        events = []
        for actor_id, actor in state.actors.items():
            if actor.economic.gdp_strength < 0.25:
                old = actor.political.domestic_stability
                actor.political.domestic_stability = _clamp(old - 0.04)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] {actor_id} GDP critically low "
                        f"({actor.economic.gdp_strength:.2f}) → "
                        f"domestic stability degrades "
                        f"({old:.2f} → {actor.political.domestic_stability:.2f})."
                    ),
                    source="cascade",
                    affected_actors=[actor_id],
                    world_state_delta={
                        f"{actor_id}.political.domestic_stability":
                            f"{old:.2f} → {actor.political.domestic_stability:.2f}"
                    },
                ))
        return events


    # ── Rule 7: Diplomatic de-escalation cascade ──────────────────────────────

    def _diplomatic_deescalation_cascade(
        self, state: WorldState, actions: Dict[str, BaseAction]
    ) -> List[GlobalEvent]:
        """
        Negotiate actions reduce bilateral threat perception and global tension.
        Mutual negotiation (both sides target each other) triggers a stronger effect.
        """
        events = []
        negotiators = {
            name: action for name, action in actions.items()
            if isinstance(action, NegotiateAction) and action.target_actor
        }

        processed_pairs: set = set()

        for actor_id, action in negotiators.items():
            target_id = action.target_actor
            pair = tuple(sorted([actor_id, target_id]))
            if pair in processed_pairs:
                continue
            processed_pairs.add(pair)

            mutual = (
                target_id in negotiators
                and negotiators[target_id].target_actor == actor_id
            )

            if mutual:
                # Both sides negotiating — meaningful bilateral signal
                tp_drop = 0.06
                tension_drop = 0.04
                trust_gain = 0.05
                for a, b in [(actor_id, target_id), (target_id, actor_id)]:
                    rel = state.get_relationship(a, b)
                    if rel:
                        rel.threat_perception = _clamp(rel.threat_perception - tp_drop)
                        rel.trust_score = _clamp(rel.trust_score + trust_gain)
                state.global_tension = _clamp(state.global_tension - tension_drop)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] Mutual negotiation: {actor_id} ↔ {target_id} → "
                        f"bilateral threat_perception −{tp_drop:.2f}, "
                        f"trust +{trust_gain:.2f}, tension −{tension_drop:.2f}."
                    ),
                    source="cascade",
                    caused_by_actor=actor_id,
                    affected_actors=[actor_id, target_id],
                    world_state_delta={
                        f"{actor_id}→{target_id}.threat_perception": f"−{tp_drop:.2f}",
                        f"{target_id}→{actor_id}.threat_perception": f"−{tp_drop:.2f}",
                        "global_tension": f"−{tension_drop:.2f}",
                    },
                ))
            else:
                # Unilateral negotiation — smaller signal
                tp_drop = 0.03
                tension_drop = 0.02
                rel = state.get_relationship(target_id, actor_id)
                if rel:
                    rel.threat_perception = _clamp(rel.threat_perception - tp_drop)
                state.global_tension = _clamp(state.global_tension - tension_drop)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] Unilateral negotiation: {actor_id} → {target_id} → "
                        f"{target_id}'s threat perception of {actor_id} −{tp_drop:.2f}, "
                        f"tension −{tension_drop:.2f}."
                    ),
                    source="cascade",
                    caused_by_actor=actor_id,
                    affected_actors=[target_id],
                    world_state_delta={
                        f"{target_id}→{actor_id}.threat_perception": f"−{tp_drop:.2f}",
                        "global_tension": f"−{tension_drop:.2f}",
                    },
                ))

        return events

    # ── Rule 8: Back-channel cascade ──────────────────────────────────────────

    def _back_channel_cascade(
        self, state: WorldState, actions: Dict[str, BaseAction]
    ) -> List[GlobalEvent]:
        """
        Back-channel diplomacy reduces the target's threat perception of the initiator
        and slightly reduces global tension. Models quiet restraint signaling.
        """
        events = []
        for actor_id, action in actions.items():
            if not isinstance(action, BackChannelAction) or not action.target_actor:
                continue
            target_id = action.target_actor
            tp_drop = 0.05
            tension_drop = 0.02

            rel = state.get_relationship(target_id, actor_id)
            if rel:
                rel.threat_perception = _clamp(rel.threat_perception - tp_drop)
            state.global_tension = _clamp(state.global_tension - tension_drop)
            events.append(GlobalEvent(
                turn=state.turn, category="cascade",
                description=(
                    f"[CASCADE] Back-channel: {actor_id} → {target_id} → "
                    f"{target_id}'s threat perception of {actor_id} −{tp_drop:.2f}, "
                    f"tension −{tension_drop:.2f}."
                ),
                source="cascade",
                caused_by_actor=actor_id,
                affected_actors=[target_id],
                world_state_delta={
                    f"{target_id}→{actor_id}.threat_perception": f"−{tp_drop:.2f}",
                    "global_tension": f"−{tension_drop:.2f}",
                },
            ))
        return events

    # ── Rule 9: Aid & alliance cascade ────────────────────────────────────────

    def _aid_and_alliance_cascade(
        self, state: WorldState, actions: Dict[str, BaseAction]
    ) -> List[GlobalEvent]:
        """
        - foreign_aid → recipient domestic stability +0.04, bilateral trust +0.05
        - intel_sharing → bilateral trust +0.04
        - form_alliance → systemic alliance cohesion +0.04
        """
        events = []

        for actor_id, action in actions.items():

            if isinstance(action, ForeignAidAction) and action.target_actor:
                target_id = action.target_actor
                recipient = state.get_actor(target_id)
                stability_gain = 0.04
                trust_gain = 0.05
                if recipient:
                    recipient.political.domestic_stability = _clamp(
                        recipient.political.domestic_stability + stability_gain
                    )
                rel = state.get_relationship(actor_id, target_id)
                if rel:
                    rel.trust_score = _clamp(rel.trust_score + trust_gain)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] Foreign aid: {actor_id} → {target_id} → "
                        f"{target_id} domestic stability +{stability_gain:.2f}, "
                        f"bilateral trust +{trust_gain:.2f}."
                    ),
                    source="cascade",
                    caused_by_actor=actor_id,
                    affected_actors=[target_id],
                    world_state_delta={
                        f"{target_id}.political.domestic_stability": f"+{stability_gain:.2f}",
                        f"{actor_id}→{target_id}.trust_score": f"+{trust_gain:.2f}",
                    },
                ))

            elif isinstance(action, IntelSharingAction) and action.target_actor:
                target_id = action.target_actor
                trust_gain = 0.04
                rel_ab = state.get_relationship(actor_id, target_id)
                rel_ba = state.get_relationship(target_id, actor_id)
                if rel_ab:
                    rel_ab.trust_score = _clamp(rel_ab.trust_score + trust_gain)
                if rel_ba:
                    rel_ba.trust_score = _clamp(rel_ba.trust_score + trust_gain)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] Intel sharing: {actor_id} → {target_id} → "
                        f"bilateral trust +{trust_gain:.2f}."
                    ),
                    source="cascade",
                    caused_by_actor=actor_id,
                    affected_actors=[actor_id, target_id],
                    world_state_delta={
                        f"{actor_id}→{target_id}.trust_score": f"+{trust_gain:.2f}",
                        f"{target_id}→{actor_id}.trust_score": f"+{trust_gain:.2f}",
                    },
                ))

            elif isinstance(action, FormAllianceAction):
                cohesion_gain = 0.04
                old = state.systemic.alliance_system_cohesion
                state.systemic.alliance_system_cohesion = _clamp(old + cohesion_gain)
                events.append(GlobalEvent(
                    turn=state.turn, category="cascade",
                    description=(
                        f"[CASCADE] Alliance formation by {actor_id} → "
                        f"alliance system cohesion +{cohesion_gain:.2f} "
                        f"({old:.2f} → {state.systemic.alliance_system_cohesion:.2f})."
                    ),
                    source="cascade",
                    caused_by_actor=actor_id,
                    affected_actors=list(state.actors.keys()),
                    world_state_delta={
                        "systemic.alliance_system_cohesion": f"+{cohesion_gain:.2f}",
                    },
                ))

        return events


def _phase_rank(phase: str) -> int:
    order = {"peacetime": 0, "tension": 1, "crisis": 2, "war": 3, "post_conflict": 1}
    return order.get(phase, 0)
