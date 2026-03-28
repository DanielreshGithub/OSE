"""
Deterministic perception building for OSE actors.

The goal is to give actors partial, state-driven views of the world without
making the simulation opaque. Noise is derived from a stable hash of the run
seed and the current turn, so identical inputs reproduce identical perception
packets.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Tuple

from world.state import Actor, WorldState


def _to_band(value: float) -> str:
    if value >= 0.70:
        return "HIGH"
    if value >= 0.40:
        return "MEDIUM"
    return "LOW"


def _to_confidence(scale: float) -> str:
    if scale <= 0.05:
        return "HIGH"
    if scale <= 0.12:
        return "MEDIUM"
    return "LOW"


def _stable_unit(seed: int, *parts: object) -> float:
    payload = "|".join(str(p) for p in (seed, *parts)).encode("utf-8")
    digest = hashlib.sha256(payload).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _stable_gaussian(seed: int, *parts: object) -> float:
    u1 = max(_stable_unit(seed, *parts, "u1"), 1e-12)
    u2 = _stable_unit(seed, *parts, "u2")
    return math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)


def _pressure_value(state: WorldState, field_name: str) -> float:
    pressures = getattr(state, "pressures", None)
    if pressures is None:
        return 0.0
    aliases = {
        "uncertainty_pressure": "uncertainty",
        "domestic_political_pressure": "domestic_pressure",
        "information_pressure": "informational_pressure",
    }
    field_name = aliases.get(field_name, field_name)
    return float(getattr(pressures, field_name, 0.0))


def _recent_turn_events(state: WorldState) -> List[Any]:
    if not state.turn_logs:
        return []
    last = state.turn_logs[-1]
    events = []
    if hasattr(last, "events_this_turn"):
        events.extend(last.events_this_turn)
    if hasattr(last, "cascade_events"):
        events.extend(last.cascade_events)
    return events


def _contradictory_signals(events: Iterable[Any]) -> List[str]:
    contradictory: List[str] = []
    markers = ("suspected", "unconfirmed", "contradict", "unclear", "ambiguous")
    for event in events:
        desc = getattr(event, "description", "")
        lowered = desc.lower()
        if any(marker in lowered for marker in markers):
            contradictory.append(desc)
    return contradictory


def _recent_alliance_intel_bonus(actor: Actor, state: WorldState) -> float:
    if not state.turn_logs:
        return 0.0
    last_log = state.turn_logs[-1]
    decisions = getattr(last_log, "decisions", [])
    allies = set(state.get_allies(actor.short_name, min_strength=0.3))
    bonus = 0.0
    for record in decisions:
        action = record.parsed_action or {}
        if (
            record.actor_short_name in allies
            and action.get("action_type") == "intel_sharing"
            and action.get("target_actor") == actor.short_name
        ):
            bonus += 0.04
    return min(0.08, bonus)


def _per_field_noise_scale(
    actor: Actor,
    other_name: str,
    state: WorldState,
    contradictory_count: int,
) -> float:
    base = max(0.0, 1.0 - actor.information_quality)
    uncertainty = _pressure_value(state, "uncertainty_pressure")
    intel_bonus = _recent_alliance_intel_bonus(actor, state)
    if other_name == actor.short_name:
        relation_scale = 0.0
    elif other_name in set(state.get_allies(actor.short_name)):
        relation_scale = 0.03
    elif other_name in set(state.get_adversaries(actor.short_name)):
        relation_scale = 0.08 + base * 0.20
    else:
        relation_scale = 0.06 + base * 0.10
    scale = relation_scale + (uncertainty * 0.12) + (contradictory_count * 0.01) - intel_bonus
    return max(0.0, min(0.25, scale))


def _resource_fields(other: Actor) -> Dict[str, float]:
    return {
        "conventional_forces": other.military.conventional_forces,
        "naval_power": other.military.naval_power,
        "air_superiority": other.military.air_superiority,
        "nuclear_capability": other.military.nuclear_capability,
        "readiness": other.military.readiness,
        "amphibious_capacity": other.military.amphibious_capacity,
        "a2ad_effectiveness": other.military.a2ad_effectiveness,
        "gdp_strength": other.economic.gdp_strength,
        "foreign_reserves": other.economic.foreign_reserves,
        "energy_independence": other.economic.energy_independence,
        "trade_openness": other.economic.trade_openness,
        "industrial_capacity": other.economic.industrial_capacity,
        "domestic_stability": other.political.domestic_stability,
        "regime_legitimacy": other.political.regime_legitimacy,
        "international_standing": other.political.international_standing,
        "decision_unity": other.political.decision_unity,
        "casualty_tolerance": other.political.casualty_tolerance,
    }


def build_perception_packet(actor: Actor, state: WorldState) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Build a deterministic, actor-specific view of the world.

    Returns:
      - packet: bounded qualitative view sent to the LLM
      - metadata: structured audit information for logs
    """
    seed = int(getattr(state, "random_seed", 0))
    recent_events = _recent_turn_events(state)
    contradictory = _contradictory_signals(recent_events)
    contradictory_count = len(contradictory)
    packet: Dict[str, Any] = {
        "self": {},
        "others": {},
        "relationships": [],
        "systemic": {
            "semiconductor_supply_chain": _to_band(state.systemic.semiconductor_supply_chain_integrity),
            "global_shipping_disruption": _to_band(state.systemic.global_shipping_disruption),
            "energy_market_volatility": _to_band(state.systemic.energy_market_volatility),
            "alliance_system_cohesion": _to_band(state.systemic.alliance_system_cohesion),
        },
        "uncertainty": {
            "level": _to_band(_pressure_value(state, "uncertainty_pressure")),
            "contradictory_signals": contradictory[:3],
        },
    }
    metadata: Dict[str, Any] = {
        "seed": seed,
        "turn": state.turn,
        "uncertainty_pressure": round(_pressure_value(state, "uncertainty_pressure"), 3),
        "contradictory_signal_count": contradictory_count,
        "actors": {},
    }

    for other_name, other in state.actors.items():
        noise_scale = _per_field_noise_scale(actor, other_name, state, contradictory_count)
        other_packet: Dict[str, Any] = {
            "posture": other.current_posture,
            "assessment_confidence": _to_confidence(noise_scale),
        }
        actor_meta: Dict[str, Any] = {
            "noise_scale": round(noise_scale, 4),
            "assessment_confidence": _to_confidence(noise_scale),
            "fields": {},
        }
        for field_name, value in _resource_fields(other).items():
            if other_name == actor.short_name:
                perceived = value
                noise = 0.0
            else:
                noise = _stable_gaussian(seed, state.turn, actor.short_name, other_name, field_name) * noise_scale
                perceived = max(0.0, min(1.0, value + noise))
            other_packet[field_name] = _to_band(perceived)
            actor_meta["fields"][field_name] = {
                "perceived": round(perceived, 4),
                "noise": round(noise, 4),
            }
        if hasattr(other, "capabilities") and getattr(other, "capabilities") is not None:
            caps = getattr(other, "capabilities")
            capability_bands = {}
            for field_name in getattr(caps.__class__, "model_fields", {}):
                raw = getattr(caps, field_name)
                if isinstance(raw, float):
                    capability_bands[field_name] = _to_band(raw)
            if capability_bands:
                other_packet["capabilities"] = capability_bands
        if other_name == actor.short_name:
            packet["self"] = other_packet
        else:
            packet["others"][other_name] = other_packet
        metadata["actors"][other_name] = actor_meta

    for rel in state.relationships:
        if rel.from_actor != actor.short_name:
            continue
        packet["relationships"].append({
            "with": rel.to_actor,
            "type": rel.relationship_type,
            "trust": _to_band(rel.trust_score),
            "alliance_strength": _to_band(rel.alliance_strength),
            "threat_perception": _to_band(rel.threat_perception),
            "deterrence_credibility": _to_band(rel.deterrence_credibility),
        })

    metadata["packet_size_bytes"] = len(json.dumps(packet))
    return packet, metadata
