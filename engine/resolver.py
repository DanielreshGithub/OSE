"""
TurnResolver — simultaneous action resolution with conflict adjudication.

All actors submit actions in parallel; no turn-order bias.
The resolver pairs conflicting actions (e.g., mutual strikes) and applies
diminishing returns or mitigation before writing to world state.

Resolution order:
  1. Detect conflict pairs (Strike vs Strike, Strike vs DefensivePosture)
  2. Apply military actions with adjudicated effectiveness
  3. Apply diplomatic actions
  4. Apply economic actions
  5. Apply information actions
  6. Apply inaction (no-op, but logged)
  7. Update global_tension
  8. Clamp all resource floats to [0, 1]
"""
from __future__ import annotations

from typing import Dict, List, Tuple, Any

from world.state import WorldState, Actor
from world.events import GlobalEvent
from engine.actions import (
    BaseAction,
    MobilizeAction, StrikeAction, AdvanceAction, WithdrawAction,
    BlockadeAction, DefensivePostureAction, ProbeAction, SignalResolveAction,
    NegotiateAction, TargetedSanctionAction, ComprehensiveSanctionAction,
    FormAllianceAction, CondemnAction, IntelSharingAction, BackChannelAction,
    EmbargoAction, ForeignAidAction, CutSupplyAction, TechnologyRestrictionAction,
    PropagandaAction, PartialCoercionAction, CyberOperationAction,
    NuclearSignalAction,
    HoldPositionAction, MonitorAction,
)

INTENSITY_SCALE = {"low": 0.5, "medium": 1.0, "high": 1.5}


def _scale(base: float, action: BaseAction) -> float:
    return base * INTENSITY_SCALE.get(action.intensity, 1.0)


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


class TurnResolver:
    """
    Resolves all actors' simultaneous actions for one turn.
    Returns the mutated world state and a list of GlobalEvents produced.
    """

    def resolve(
        self,
        decisions: Dict[str, Tuple[BaseAction, Any]],
        state: WorldState,
    ) -> Tuple[WorldState, List[GlobalEvent]]:
        """
        decisions: {actor_short_name: (action, decision_record)}
        Returns (mutated_state, events_this_turn)
        """
        events: List[GlobalEvent] = []
        actions = {name: act for name, (act, _) in decisions.items()}

        # ── Detect conflict pairs ─────────────────────────────────────────────
        strike_targets: Dict[str, str] = {}  # actor -> target_actor
        defensive_actors: set = set()

        for actor_id, action in actions.items():
            if isinstance(action, StrikeAction) and action.target_actor:
                strike_targets[actor_id] = action.target_actor
            if isinstance(action, DefensivePostureAction):
                defensive_actors.add(actor_id)

        # Mutual strike pairs: A strikes B AND B strikes A
        mutual_strikes: set = set()
        for a, target in strike_targets.items():
            if target in strike_targets and strike_targets[target] == a:
                pair = frozenset({a, target})
                mutual_strikes.add(pair)

        # ── Apply actions ─────────────────────────────────────────────────────
        tension_delta = 0.0

        for actor_id, action in actions.items():
            actor = state.get_actor(actor_id)
            if actor is None:
                continue

            # ── Military ─────────────────────────────────────────────────────

            if isinstance(action, MobilizeAction):
                gain = _scale(0.18, action)
                actor.military.readiness = _clamp(actor.military.readiness + gain)
                actor.military.logistics_capacity = _clamp(
                    actor.military.logistics_capacity - _scale(0.04, action)
                )
                actor.economic.gdp_strength = _clamp(
                    actor.economic.gdp_strength - action.economic_cost
                )
                actor.current_posture = "escalatory"
                tension_delta += _scale(0.04, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=f"{actor_id} mobilizes forces (readiness +{gain:.2f}).",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=list(state.actors.keys()),
                ))

            elif isinstance(action, StrikeAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target is None:
                    continue

                pair = frozenset({actor_id, action.target_actor})
                is_mutual = pair in mutual_strikes
                target_defensive = action.target_actor in defensive_actors

                if is_mutual:
                    effectiveness = 0.70
                elif target_defensive:
                    effectiveness = 0.60
                else:
                    effectiveness = 1.0

                # Damage to target
                dmg = _scale(0.14, action) * effectiveness
                target.military.conventional_forces = _clamp(
                    target.military.conventional_forces - dmg
                )
                target.military.readiness = _clamp(target.military.readiness - dmg * 0.5)

                # Attrition to attacker
                attrition = _scale(0.05, action)
                actor.military.conventional_forces = _clamp(
                    actor.military.conventional_forces - attrition
                )
                actor.military.readiness = _clamp(actor.military.readiness - action.military_cost)
                actor.political.domestic_stability = _clamp(
                    actor.political.domestic_stability - action.political_cost
                )

                tension_delta += _scale(0.15, action)
                desc = (
                    f"{actor_id} strikes {action.target_actor} "
                    f"({'mutual' if is_mutual else 'vs defensive' if target_defensive else 'uncontested'}, "
                    f"eff={effectiveness:.0%}). Target forces -{dmg:.2f}."
                )
                events.append(GlobalEvent(
                    turn=state.turn, category="military", description=desc,
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, AdvanceAction) and action.target_zone:
                gain = _scale(0.12, action)
                if action.target_zone not in actor.territory.contested_zones:
                    actor.territory.contested_zones[action.target_zone] = 0.0
                actor.territory.contested_zones[action.target_zone] = _clamp(
                    actor.territory.contested_zones[action.target_zone] + gain
                )
                actor.military.logistics_capacity = _clamp(
                    actor.military.logistics_capacity - _scale(0.06, action)
                )
                tension_delta += _scale(0.06, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=f"{actor_id} advances into {action.target_zone} (control +{gain:.2f}).",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=list(state.actors.keys()),
                ))

            elif isinstance(action, WithdrawAction):
                actor.military.readiness = _clamp(actor.military.readiness - 0.08)
                actor.current_posture = "cautious"
                tension_delta -= 0.04
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=f"{actor_id} withdraws forces (de-escalatory signal).",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=list(state.actors.keys()),
                ))

            elif isinstance(action, BlockadeAction):
                target_id = action.target_actor or action.target_zone
                if action.target_actor:
                    target = state.get_actor(action.target_actor)
                    if target:
                        target.economic.trade_openness = _clamp(
                            target.economic.trade_openness - _scale(0.18, action)
                        )
                state.systemic.global_shipping_disruption = _clamp(
                    state.systemic.global_shipping_disruption + _scale(0.10, action)
                )
                tension_delta += _scale(0.08, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=f"{actor_id} enforces blockade against {target_id}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id] + ([action.target_actor] if action.target_actor else []),
                ))

            elif isinstance(action, DefensivePostureAction):
                actor.military.a2ad_effectiveness = _clamp(
                    actor.military.a2ad_effectiveness + _scale(0.08, action)
                )
                actor.current_posture = "defensive"
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=f"{actor_id} adopts defensive posture (A2/AD +{_scale(0.08, action):.2f}).",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id],
                ))

            elif isinstance(action, ProbeAction):
                actor.information_quality = _clamp(
                    actor.information_quality + _scale(0.04, action)
                )
                tension_delta += _scale(0.02, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=f"{actor_id} conducts probe operation (intel quality +{_scale(0.04, action):.2f}).",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id],
                ))

            elif isinstance(action, SignalResolveAction):
                for rel in state.relationships:
                    if rel.from_actor in state.get_allies(actor_id) and rel.to_actor == actor_id:
                        rel.deterrence_credibility = _clamp(rel.deterrence_credibility + 0.06)
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=f"{actor_id} signals resolve publicly.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=list(state.actors.keys()),
                ))

            # ── Diplomatic ────────────────────────────────────────────────────

            elif isinstance(action, NegotiateAction) and action.target_actor:
                rel = state.get_relationship(actor_id, action.target_actor)
                if rel:
                    rel.trust_score = _clamp(rel.trust_score + _scale(0.08, action))
                tension_delta -= _scale(0.06, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=f"{actor_id} opens negotiations with {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, TargetedSanctionAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.economic.gdp_strength = _clamp(
                        target.economic.gdp_strength - _scale(0.05, action)
                    )
                    target.political.international_standing = _clamp(
                        target.political.international_standing - _scale(0.03, action)
                    )
                actor.economic.trade_openness = _clamp(
                    actor.economic.trade_openness - action.economic_cost
                )
                tension_delta += _scale(0.03, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=(
                        f"{actor_id} imposes targeted sanctions on {action.target_actor} "
                        f"(sector-specific, graduated signal)."
                    ),
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, ComprehensiveSanctionAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.economic.gdp_strength = _clamp(
                        target.economic.gdp_strength - _scale(0.16, action)
                    )
                    target.economic.trade_openness = _clamp(
                        target.economic.trade_openness - _scale(0.18, action)
                    )
                    target.political.international_standing = _clamp(
                        target.political.international_standing - _scale(0.06, action)
                    )
                actor.economic.gdp_strength = _clamp(
                    actor.economic.gdp_strength - action.economic_cost
                )
                actor.economic.trade_openness = _clamp(
                    actor.economic.trade_openness - 0.05
                )
                tension_delta += _scale(0.08, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=(
                        f"{actor_id} imposes comprehensive sanctions on {action.target_actor} "
                        f"(full economic warfare — high blowback for both parties)."
                    ),
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, FormAllianceAction) and action.target_actor:
                rel = state.get_relationship(actor_id, action.target_actor)
                if rel:
                    rel.relationship_type = "ally"
                    rel.alliance_strength = _clamp(rel.alliance_strength + _scale(0.20, action))
                state.systemic.alliance_system_cohesion = _clamp(
                    state.systemic.alliance_system_cohesion + 0.04
                )
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=f"{actor_id} formalizes alliance with {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, CondemnAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.political.international_standing = _clamp(
                        target.political.international_standing - _scale(0.05, action)
                    )
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=f"{actor_id} publicly condemns {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, IntelSharingAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.information_quality = _clamp(
                        target.information_quality + _scale(0.07, action)
                    )
                rel = state.get_relationship(actor_id, action.target_actor)
                if rel:
                    rel.trust_score = _clamp(rel.trust_score + 0.05)
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=f"{actor_id} shares intelligence with {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, BackChannelAction) and action.target_actor:
                rel = state.get_relationship(actor_id, action.target_actor)
                if rel:
                    rel.trust_score = _clamp(rel.trust_score + _scale(0.04, action))
                tension_delta -= _scale(0.03, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=f"{actor_id} opens back-channel with {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            # ── Economic ──────────────────────────────────────────────────────

            elif isinstance(action, EmbargoAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.economic.trade_openness = _clamp(
                        target.economic.trade_openness - _scale(0.18, action)
                    )
                    target.economic.gdp_strength = _clamp(
                        target.economic.gdp_strength - _scale(0.10, action)
                    )
                actor.economic.gdp_strength = _clamp(
                    actor.economic.gdp_strength - action.economic_cost
                )
                state.systemic.global_shipping_disruption = _clamp(
                    state.systemic.global_shipping_disruption + 0.04
                )
                tension_delta += _scale(0.05, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="economic",
                    description=f"{actor_id} imposes embargo on {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, ForeignAidAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.economic.gdp_strength = _clamp(
                        target.economic.gdp_strength + _scale(0.05, action)
                    )
                actor.economic.foreign_reserves = _clamp(
                    actor.economic.foreign_reserves - action.economic_cost
                )
                rel = state.get_relationship(actor_id, action.target_actor)
                if rel:
                    rel.trust_score = _clamp(rel.trust_score + 0.06)
                    rel.alliance_strength = _clamp(rel.alliance_strength + 0.04)
                events.append(GlobalEvent(
                    turn=state.turn, category="economic",
                    description=f"{actor_id} provides foreign aid to {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, CutSupplyAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.economic.industrial_capacity = _clamp(
                        target.economic.industrial_capacity - _scale(0.08, action)
                    )
                state.systemic.semiconductor_supply_chain_integrity = _clamp(
                    state.systemic.semiconductor_supply_chain_integrity - _scale(0.05, action)
                )
                tension_delta += _scale(0.04, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="economic",
                    description=f"{actor_id} cuts supply to {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, TechnologyRestrictionAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.economic.industrial_capacity = _clamp(
                        target.economic.industrial_capacity - _scale(0.14, action)
                    )
                    target.military.readiness = _clamp(
                        target.military.readiness - _scale(0.04, action)
                    )
                actor.economic.trade_openness = _clamp(
                    actor.economic.trade_openness - action.economic_cost
                )
                state.systemic.semiconductor_supply_chain_integrity = _clamp(
                    state.systemic.semiconductor_supply_chain_integrity - _scale(0.08, action)
                )
                tension_delta += _scale(0.05, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="economic",
                    description=(
                        f"{actor_id} imposes technology restrictions on {action.target_actor} "
                        f"(export controls — long-duration capability denial)."
                    ),
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            # ── Information / Cyber ───────────────────────────────────────────

            elif isinstance(action, PropagandaAction):
                actor.political.domestic_stability = _clamp(
                    actor.political.domestic_stability + _scale(0.04, action)
                )
                if action.target_actor:
                    target = state.get_actor(action.target_actor)
                    if target:
                        target.political.international_standing = _clamp(
                            target.political.international_standing - _scale(0.04, action)
                        )
                events.append(GlobalEvent(
                    turn=state.turn, category="information",
                    description=f"{actor_id} runs propaganda campaign.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id] + ([action.target_actor] if action.target_actor else []),
                ))

            elif isinstance(action, PartialCoercionAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.political.regime_legitimacy = _clamp(
                        target.political.regime_legitimacy - _scale(0.05, action)
                    )
                    target.economic.gdp_strength = _clamp(
                        target.economic.gdp_strength - _scale(0.04, action)
                    )
                tension_delta += _scale(0.06, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=f"{actor_id} applies partial coercion against {action.target_actor}.",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            elif isinstance(action, CyberOperationAction) and action.target_actor:
                target = state.get_actor(action.target_actor)
                if target:
                    target.economic.industrial_capacity = _clamp(
                        target.economic.industrial_capacity - _scale(0.06, action)
                    )
                    target.information_quality = _clamp(
                        target.information_quality - _scale(0.04, action)
                    )
                # Low tension impact — cyber ops are deniable gray-zone
                tension_delta += _scale(0.02, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="information",
                    description=(
                        f"{actor_id} conducts cyber operation against {action.target_actor} "
                        f"(deniable; target industrial capacity and C2 degraded)."
                    ),
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id, action.target_actor],
                ))

            # ── Nuclear ───────────────────────────────────────────────────────

            elif isinstance(action, NuclearSignalAction):
                # Raise adversary threat perception dramatically; raise own deterrence credibility
                for rel in state.relationships:
                    if rel.from_actor == actor_id:
                        rel_type = rel.relationship_type
                        if rel_type in ("adversary", "hostile", "competitor"):
                            rel.threat_perception = _clamp(
                                rel.threat_perception + _scale(0.18, action)
                            )
                        elif rel_type in ("ally", "partner"):
                            rel.deterrence_credibility = _clamp(
                                rel.deterrence_credibility + _scale(0.10, action)
                            )
                actor.political.domestic_stability = _clamp(
                    actor.political.domestic_stability - action.political_cost
                )
                tension_delta += _scale(0.14, action)
                events.append(GlobalEvent(
                    turn=state.turn, category="military",
                    description=(
                        f"{actor_id} issues nuclear posture signal — raises alert level, "
                        f"disperses strategic assets. Adversary threat perception sharply elevated."
                    ),
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=list(state.actors.keys()),
                ))

            # ── Inaction ──────────────────────────────────────────────────────
            elif isinstance(action, (HoldPositionAction, MonitorAction)):
                if isinstance(action, MonitorAction):
                    actor.information_quality = _clamp(actor.information_quality + 0.02)
                events.append(GlobalEvent(
                    turn=state.turn, category="diplomatic",
                    description=f"{actor_id} takes no action ({action.action_type}).",
                    source="actor", caused_by_actor=actor_id,
                    affected_actors=[actor_id],
                ))

        # ── Update global tension ─────────────────────────────────────────────
        state.global_tension = _clamp(state.global_tension + tension_delta)

        # ── Clamp all resource floats ─────────────────────────────────────────
        state.clamp_all_resources()

        return state, events
