"""
Action cost and effect helpers for OSE.

The goal is to keep costs explicit and interpretable instead of folding them
into one opaque formula.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Literal

from pydantic import BaseModel, Field

from world.capabilities import CapabilityVector
from world.pressures import PressureState


Intensity = Literal["low", "medium", "high"]


class ActionCostProfile(BaseModel):
    """Base cost profile for an action type."""

    military_cost: float = Field(ge=0.0, le=1.0, default=0.0)
    economic_cost: float = Field(ge=0.0, le=1.0, default=0.0)
    political_cost: float = Field(ge=0.0, le=1.0, default=0.0)
    uncertainty_cost: float = Field(ge=-1.0, le=1.0, default=0.0)
    tension_impact: float = Field(ge=-1.0, le=1.0, default=0.0)
    downstream_risk: float = Field(ge=0.0, le=1.0, default=0.0)
    notes: str = ""

    model_config = {"extra": "forbid"}


class ActionEffectModifier(BaseModel):
    """Deterministic modifier applied to an action cost/effect profile."""

    military_multiplier: float = Field(ge=0.0, le=3.0, default=1.0)
    economic_multiplier: float = Field(ge=0.0, le=3.0, default=1.0)
    political_multiplier: float = Field(ge=0.0, le=3.0, default=1.0)
    tension_multiplier: float = Field(ge=0.0, le=3.0, default=1.0)
    risk_multiplier: float = Field(ge=0.0, le=3.0, default=1.0)
    explanation: str = ""

    model_config = {"extra": "forbid"}


class ActionCostBreakdown(BaseModel):
    """Final cost breakdown after base profile plus modifiers."""

    military_cost: float
    economic_cost: float
    political_cost: float
    uncertainty_cost: float
    tension_impact: float
    downstream_risk: float
    explanation: str = ""

    model_config = {"extra": "forbid"}


BASE_ACTION_COSTS: Dict[str, ActionCostProfile] = {
    "mobilize": ActionCostProfile(military_cost=0.10, economic_cost=0.05, tension_impact=0.04, downstream_risk=0.15),
    "strike": ActionCostProfile(military_cost=0.20, political_cost=0.15, uncertainty_cost=0.05, tension_impact=0.15, downstream_risk=0.35),
    "advance": ActionCostProfile(military_cost=0.15, tension_impact=0.06, downstream_risk=0.20),
    "withdraw": ActionCostProfile(military_cost=0.05, tension_impact=-0.04, downstream_risk=0.05),
    "blockade": ActionCostProfile(military_cost=0.15, economic_cost=0.05, tension_impact=0.08, downstream_risk=0.25),
    "defensive_posture": ActionCostProfile(military_cost=0.05, tension_impact=0.00, downstream_risk=0.10),
    "probe": ActionCostProfile(military_cost=0.05, uncertainty_cost=-0.04, tension_impact=0.02, downstream_risk=0.12),
    "signal_resolve": ActionCostProfile(political_cost=0.02, tension_impact=0.01, downstream_risk=0.08),
    "deploy_forward": ActionCostProfile(military_cost=0.12, political_cost=0.04, tension_impact=0.05, downstream_risk=0.18),
    "negotiate": ActionCostProfile(political_cost=0.05, tension_impact=-0.06, downstream_risk=0.10),
    "targeted_sanction": ActionCostProfile(economic_cost=0.03, political_cost=0.03, tension_impact=0.03, downstream_risk=0.12),
    "comprehensive_sanction": ActionCostProfile(economic_cost=0.10, political_cost=0.08, tension_impact=0.08, downstream_risk=0.25),
    "form_alliance": ActionCostProfile(political_cost=0.06, tension_impact=0.02, downstream_risk=0.15),
    "condemn": ActionCostProfile(political_cost=0.01, tension_impact=0.01, downstream_risk=0.04),
    "intel_sharing": ActionCostProfile(political_cost=0.02, uncertainty_cost=-0.05, downstream_risk=0.08),
    "back_channel": ActionCostProfile(political_cost=0.01, tension_impact=-0.03, downstream_risk=0.06),
    "lawfare_filing": ActionCostProfile(political_cost=0.03, tension_impact=-0.01, downstream_risk=0.05),
    "multilateral_appeal": ActionCostProfile(political_cost=0.03, tension_impact=-0.03, downstream_risk=0.06),
    "expel_diplomats": ActionCostProfile(political_cost=0.05, tension_impact=0.04, downstream_risk=0.10),
    "embargo": ActionCostProfile(economic_cost=0.10, tension_impact=0.05, downstream_risk=0.18),
    "foreign_aid": ActionCostProfile(economic_cost=0.08, political_cost=0.02, tension_impact=-0.01, downstream_risk=0.08),
    "cut_supply": ActionCostProfile(economic_cost=0.04, tension_impact=0.04, downstream_risk=0.15),
    "technology_restriction": ActionCostProfile(economic_cost=0.05, tension_impact=0.05, downstream_risk=0.18),
    "asset_freeze": ActionCostProfile(economic_cost=0.04, political_cost=0.03, tension_impact=0.04, downstream_risk=0.14),
    "supply_chain_diversion": ActionCostProfile(economic_cost=0.05, political_cost=0.02, tension_impact=0.01, downstream_risk=0.10),
    "propaganda": ActionCostProfile(political_cost=0.01, uncertainty_cost=0.02, tension_impact=0.01, downstream_risk=0.06),
    "partial_coercion": ActionCostProfile(military_cost=0.04, political_cost=0.05, tension_impact=0.06, downstream_risk=0.20),
    "cyber_operation": ActionCostProfile(economic_cost=0.02, uncertainty_cost=0.03, tension_impact=0.02, downstream_risk=0.16),
    "hack_and_leak": ActionCostProfile(economic_cost=0.02, political_cost=0.04, uncertainty_cost=0.04, tension_impact=0.03, downstream_risk=0.18),
    "nuclear_signal": ActionCostProfile(political_cost=0.08, tension_impact=0.14, downstream_risk=0.40),
    "hold_position": ActionCostProfile(tension_impact=0.00, downstream_risk=0.02),
    "monitor": ActionCostProfile(uncertainty_cost=-0.02, tension_impact=0.00, downstream_risk=0.03),
}


INTENSITY_SCALE: Dict[Intensity, float] = {
    "low": 0.5,
    "medium": 1.0,
    "high": 1.5,
}


def scale_profile(profile: ActionCostProfile, intensity: Intensity = "medium") -> ActionCostProfile:
    """Scale the profile by action intensity."""
    scale = INTENSITY_SCALE.get(intensity, 1.0)
    return ActionCostProfile(
        military_cost=profile.military_cost * scale,
        economic_cost=profile.economic_cost * scale,
        political_cost=profile.political_cost * scale,
        uncertainty_cost=profile.uncertainty_cost * scale,
        tension_impact=profile.tension_impact * scale,
        downstream_risk=profile.downstream_risk * scale,
        notes=profile.notes,
    )


def capability_multiplier(capabilities: CapabilityVector, action_type: str) -> ActionEffectModifier:
    """
    Derive deterministic effect multipliers from actor capability strengths.

    This is intentionally readable and coarse-grained.
    """
    c = capabilities.as_numeric()

    military = 1.0
    economic = 1.0
    political = 1.0
    tension = 1.0
    risk = 1.0
    explanation = []

    if action_type in {"strike", "advance", "blockade", "partial_coercion", "deploy_forward"}:
        military *= max(0.75, 1.15 - 0.35 * c["logistics_endurance"])
        tension *= 1.0 + (0.20 * c["escalation_tolerance"])
        risk *= 1.0 - (0.15 * c["intelligence_quality"])
        explanation.append("military posture and logistics shape hard-power execution")

    if action_type in {"embargo", "targeted_sanction", "comprehensive_sanction", "technology_restriction", "cut_supply", "asset_freeze", "supply_chain_diversion"}:
        economic *= max(0.80, 1.10 - 0.30 * c["economic_coercion_capacity"])
        risk *= 1.0 - (0.10 * c["alliance_leverage"])
        explanation.append("economic coercion capacity affects cost discipline")

    if action_type in {"intel_sharing", "monitor", "probe", "back_channel", "lawfare_filing", "multilateral_appeal", "expel_diplomats"}:
        political *= max(0.80, 1.05 - 0.20 * c["bureaucratic_flexibility"])
        tension *= max(0.80, 1.0 - 0.10 * c["signaling_credibility"])
        explanation.append("bureaucratic flexibility and signaling affect low-intensity moves")

    if action_type in {"cyber_operation", "hack_and_leak"}:
        risk *= max(0.75, 1.10 - 0.25 * c["cyber_capability"])
        political *= max(0.85, 1.05 - 0.15 * c["intelligence_quality"])
        explanation.append("cyber capability and intelligence quality shape deniable operations")

    if action_type == "nuclear_signal":
        political *= max(0.85, 1.10 - 0.25 * c["war_aversion"])
        risk *= 1.25
        tension *= 1.15
        explanation.append("nuclear signaling is highly sensitive to war aversion")

    return ActionEffectModifier(
        military_multiplier=military,
        economic_multiplier=economic,
        political_multiplier=political,
        tension_multiplier=tension,
        risk_multiplier=risk,
        explanation="; ".join(explanation) if explanation else "baseline capability adjustment",
    )


def compute_action_cost_breakdown(
    action_type: str,
    capabilities: CapabilityVector,
    pressures: PressureState | None = None,
    intensity: Intensity = "medium",
) -> ActionCostBreakdown:
    """Compute a deterministic cost breakdown for a planned action."""
    base = BASE_ACTION_COSTS.get(action_type, ActionCostProfile())
    scaled = scale_profile(base, intensity)
    modifier = capability_multiplier(capabilities, action_type)

    pressure_scale = 1.0
    if pressures is not None:
        pressure_scale += 0.15 * pressures.crisis_instability + 0.10 * pressures.military_pressure + 0.08 * pressures.economic_pressure

    military_cost = scaled.military_cost * modifier.military_multiplier * pressure_scale
    economic_cost = scaled.economic_cost * modifier.economic_multiplier * pressure_scale
    political_cost = scaled.political_cost * modifier.political_multiplier * pressure_scale
    uncertainty_cost = scaled.uncertainty_cost * pressure_scale
    tension_impact = scaled.tension_impact * modifier.tension_multiplier
    downstream_risk = min(1.0, scaled.downstream_risk * modifier.risk_multiplier * pressure_scale)

    return ActionCostBreakdown(
        military_cost=round(military_cost, 3),
        economic_cost=round(economic_cost, 3),
        political_cost=round(political_cost, 3),
        uncertainty_cost=round(uncertainty_cost, 3),
        tension_impact=round(tension_impact, 3),
        downstream_risk=round(downstream_risk, 3),
        explanation=modifier.explanation,
    )
