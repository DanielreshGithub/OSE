"""
Engine-side capability helpers.

These functions translate actor state into normalized capability vectors and
evaluate whether an action is feasible under current material and political
constraints.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field

from world.capabilities import CapabilityVector

if TYPE_CHECKING:
    from world.state import Actor, WorldState
    from world.pressures import PressureState


class ActionConstraint(BaseModel):
    """Bounded requirement set for one action type."""

    min_capabilities: Dict[str, float] = Field(default_factory=dict)
    max_capabilities: Dict[str, float] = Field(default_factory=dict)
    min_pressures: Dict[str, float] = Field(default_factory=dict)
    max_pressures: Dict[str, float] = Field(default_factory=dict)
    requires_target_actor: bool = False
    requires_target_zone: bool = False
    requires_visibility: bool = False
    requires_intelligence: bool = False
    theater_tags: List[str] = Field(default_factory=list)
    notes: str = ""

    model_config = {"extra": "forbid"}


class FeasibilityResult(BaseModel):
    """Structured feasibility result for validator and logging."""

    eligible: bool
    reasons: List[str] = Field(default_factory=list)
    capability_gaps: Dict[str, float] = Field(default_factory=dict)
    capability_strengths: Dict[str, float] = Field(default_factory=dict)
    pressure_gaps: Dict[str, float] = Field(default_factory=dict)
    pressure_strengths: Dict[str, float] = Field(default_factory=dict)
    constraint: Optional[str] = None

    model_config = {"extra": "forbid"}


class CapabilitySummary(BaseModel):
    """Prompt-friendly capability summary."""

    actor_short_name: str
    capabilities: CapabilityVector
    bands: Dict[str, str]
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = {"extra": "forbid"}


ACTION_CONSTRAINTS: Dict[str, ActionConstraint] = {
    "mobilize": ActionConstraint(
        min_capabilities={"logistics_endurance": 0.30, "escalation_tolerance": 0.20},
        notes="Mobilization requires sustainment and some tolerance for escalation.",
    ),
    "strike": ActionConstraint(
        min_capabilities={"local_naval_projection": 0.20, "local_air_projection": 0.20, "escalation_tolerance": 0.35},
        requires_target_actor=True,
        requires_visibility=True,
        notes="Strike requires local force projection and a visible target.",
    ),
    "advance": ActionConstraint(
        min_capabilities={"logistics_endurance": 0.30, "local_naval_projection": 0.15},
        requires_target_zone=True,
        notes="Advance requires theater access and sustainment.",
    ),
    "withdraw": ActionConstraint(notes="Withdrawal remains broadly feasible."),
    "blockade": ActionConstraint(
        min_capabilities={"local_naval_projection": 0.30, "logistics_endurance": 0.25},
        requires_target_actor=True,
        notes="Blockade depends on naval access and persistence.",
    ),
    "defensive_posture": ActionConstraint(min_capabilities={"missile_a2ad_capability": 0.10}),
    "probe": ActionConstraint(
        min_capabilities={"intelligence_quality": 0.20},
        requires_target_actor=True,
        notes="Probe requires some intelligence and a target of interest.",
    ),
    "signal_resolve": ActionConstraint(min_capabilities={"signaling_credibility": 0.10}),
    "deploy_forward": ActionConstraint(
        min_capabilities={"logistics_endurance": 0.35, "local_naval_projection": 0.20},
        requires_target_zone=True,
        notes="Forward deployment requires reach, sustainment, and a destination.",
    ),
    "negotiate": ActionConstraint(min_capabilities={"domestic_stability": 0.20}),
    "targeted_sanction": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.20}, requires_target_actor=True),
    "comprehensive_sanction": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.40}, requires_target_actor=True),
    "form_alliance": ActionConstraint(min_capabilities={"alliance_leverage": 0.35}, requires_target_actor=True),
    "condemn": ActionConstraint(),
    "intel_sharing": ActionConstraint(min_capabilities={"intelligence_quality": 0.20}, requires_target_actor=True),
    "back_channel": ActionConstraint(min_capabilities={"bureaucratic_flexibility": 0.10}, requires_target_actor=True),
    "lawfare_filing": ActionConstraint(min_capabilities={"signaling_credibility": 0.25}, notes="Legal contestation requires some standing and procedural capacity."),
    "multilateral_appeal": ActionConstraint(min_capabilities={"alliance_leverage": 0.20, "signaling_credibility": 0.20}),
    "expel_diplomats": ActionConstraint(min_capabilities={"bureaucratic_flexibility": 0.20}, requires_target_actor=True),
    "embargo": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.35}, requires_target_actor=True),
    "foreign_aid": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.20}, requires_target_actor=True),
    "cut_supply": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.25}, requires_target_actor=True),
    "technology_restriction": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.25}, requires_target_actor=True),
    "asset_freeze": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.30}, requires_target_actor=True),
    "supply_chain_diversion": ActionConstraint(min_capabilities={"economic_coercion_capacity": 0.25, "logistics_endurance": 0.20}),
    "propaganda": ActionConstraint(min_capabilities={"signaling_credibility": 0.10}),
    "partial_coercion": ActionConstraint(min_capabilities={"escalation_tolerance": 0.25}, requires_target_actor=True),
    "cyber_operation": ActionConstraint(min_capabilities={"cyber_capability": 0.25}, requires_target_actor=True),
    "hack_and_leak": ActionConstraint(min_capabilities={"cyber_capability": 0.30, "intelligence_quality": 0.30}, requires_target_actor=True),
    "nuclear_signal": ActionConstraint(min_capabilities={"signaling_credibility": 0.60, "escalation_tolerance": 0.60}),
    "hold_position": ActionConstraint(),
    "monitor": ActionConstraint(min_capabilities={"intelligence_quality": 0.10}),
}


def _band(value: float) -> str:
    if value >= 0.65:
        return "HIGH"
    if value >= 0.35:
        return "MEDIUM"
    return "LOW"


def build_actor_capabilities(actor: "Actor", state: Optional["WorldState"] = None) -> CapabilityVector:
    """
    Map actor state into the canonical capability vector.

    This stays explicit so scenario templates can override assumptions later
    without changing the engine contract.
    """
    military = actor.military
    economic = actor.economic
    political = actor.political

    local_naval_projection = military.naval_power
    local_air_projection = military.air_superiority
    missile_a2ad_capability = military.a2ad_effectiveness
    cyber_capability = max(0.0, min(1.0, actor.information_quality * 0.85))
    intelligence_quality = actor.information_quality
    economic_coercion_capacity = max(
        0.0,
        min(1.0, 0.5 * economic.gdp_strength + 0.3 * economic.trade_openness + 0.2 * economic.industrial_capacity),
    )
    alliance_leverage = max(0.0, min(1.0, political.international_standing * 0.5 + political.decision_unity * 0.25 + military.nuclear_capability * 0.25))
    logistics_endurance = military.logistics_capacity
    domestic_stability = political.domestic_stability
    war_aversion = max(0.0, min(1.0, 1.0 - political.casualty_tolerance))
    escalation_tolerance = max(0.0, min(1.0, military.readiness * 0.25 + political.decision_unity * 0.35 + political.casualty_tolerance * 0.40))
    bureaucratic_flexibility = max(0.0, min(1.0, political.decision_unity * 0.5 + actor.military.readiness * 0.25 + actor.information_quality * 0.25))
    signaling_credibility = max(0.0, min(1.0, political.international_standing * 0.4 + political.regime_legitimacy * 0.3 + political.decision_unity * 0.3))

    return CapabilityVector(
        local_naval_projection=local_naval_projection,
        local_air_projection=local_air_projection,
        missile_a2ad_capability=missile_a2ad_capability,
        cyber_capability=cyber_capability,
        intelligence_quality=intelligence_quality,
        economic_coercion_capacity=economic_coercion_capacity,
        alliance_leverage=alliance_leverage,
        logistics_endurance=logistics_endurance,
        domestic_stability=domestic_stability,
        war_aversion=war_aversion,
        escalation_tolerance=escalation_tolerance,
        bureaucratic_flexibility=bureaucratic_flexibility,
        signaling_credibility=signaling_credibility,
    ).clamp()


def summarize_actor_capabilities(actor: "Actor", state: Optional["WorldState"] = None) -> CapabilitySummary:
    capabilities = build_actor_capabilities(actor, state)
    return CapabilitySummary(
        actor_short_name=actor.short_name,
        capabilities=capabilities,
        bands=capabilities.as_bands(),
        metadata={
            "scenario_id": getattr(state, "scenario_id", None),
            "scenario_name": getattr(state, "scenario_name", None),
        },
    )


def evaluate_action_constraints(
    action_type: str,
    capabilities: CapabilityVector,
    pressures: Optional["PressureState"] = None,
) -> FeasibilityResult:
    """
    Evaluate the capability side of action eligibility.

    This does not replace the existing validator; it provides a reusable
    feasibility layer for future integration and for scenario-specific checks.
    """
    constraint = ACTION_CONSTRAINTS.get(action_type)
    if constraint is None:
        return FeasibilityResult(
            eligible=False,
            reasons=[f"Unknown action_type '{action_type}'."],
            constraint=None,
        )

    reasons: List[str] = []
    gaps: Dict[str, float] = {}
    strengths: Dict[str, float] = {}

    for field_name, minimum in constraint.min_capabilities.items():
        current = float(getattr(capabilities, field_name, 0.0))
        strengths[field_name] = current
        if current < minimum:
            gaps[field_name] = round(minimum - current, 3)
            reasons.append(f"{field_name} below minimum {minimum:.2f} (have {current:.2f}).")

    for field_name, maximum in constraint.max_capabilities.items():
        current = float(getattr(capabilities, field_name, 0.0))
        strengths[field_name] = current
        if current > maximum:
            reasons.append(f"{field_name} exceeds maximum {maximum:.2f} (have {current:.2f}).")

    pressure_gaps: Dict[str, float] = {}
    pressure_strengths: Dict[str, float] = {}
    if pressures is not None:
        pressure_values = pressures.as_numeric()
        for field_name, minimum in constraint.min_pressures.items():
            current = float(pressure_values.get(field_name, 0.0))
            pressure_strengths[field_name] = current
            if current < minimum:
                pressure_gaps[field_name] = round(minimum - current, 3)
                reasons.append(f"{field_name} below minimum pressure {minimum:.2f} (have {current:.2f}).")

        for field_name, maximum in constraint.max_pressures.items():
            current = float(pressure_values.get(field_name, 0.0))
            pressure_strengths[field_name] = current
            if current > maximum:
                reasons.append(f"{field_name} exceeds maximum pressure {maximum:.2f} (have {current:.2f}).")

    return FeasibilityResult(
        eligible=not reasons,
        reasons=reasons,
        capability_gaps=gaps,
        capability_strengths=strengths,
        pressure_gaps=pressure_gaps,
        pressure_strengths=pressure_strengths,
        constraint=action_type,
    )


def capability_bands(capabilities: CapabilityVector) -> Dict[str, str]:
    """Convenience wrapper for prompt-facing summaries."""
    return {name: _band(value) for name, value in capabilities.as_numeric().items()}


def action_requires_target(action_type: str) -> bool:
    """True when the action grammar expects a concrete target."""
    constraint = ACTION_CONSTRAINTS.get(action_type)
    return bool(constraint and (constraint.requires_target_actor or constraint.requires_target_zone))
