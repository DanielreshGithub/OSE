"""
OSE Action Space — 24 typed action classes + registry + parser.

Categories:
  Military (8):    mobilize, strike, advance, withdraw, blockade,
                   defensive_posture, probe, signal_resolve
  Diplomatic (6):  negotiate, targeted_sanction, comprehensive_sanction,
                   form_alliance, condemn, intel_sharing, back_channel
  Economic (4):    embargo, foreign_aid, cut_supply, technology_restriction
  Information (3): propaganda, partial_coercion, cyber_operation
  Nuclear (1):     nuclear_signal
  Inaction (2):    hold_position, monitor

Each action class:
  - Inherits from BaseAction (Pydantic BaseModel + ABC)
  - Implements is_valid(state) -> (bool, List[str]) — pure, no external calls
  - Implements get_expected_effects() -> Dict[str, str] — for logging/display
  - Declares resource cost fields (military_cost, economic_cost, political_cost)

The ACTION_REGISTRY maps string action_type names to classes.
parse_action_from_dict() parses raw LLM JSON into typed instances.
get_available_actions_for() returns valid action types for a given actor.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Literal, Tuple, TYPE_CHECKING
from pydantic import BaseModel, Field

from engine.capabilities import evaluate_action_constraints

if TYPE_CHECKING:
    from world.state import WorldState


# ── Base Class ────────────────────────────────────────────────────────────────

class BaseAction(BaseModel, ABC):
    action_type: str
    actor_id: str                        # short_name of acting actor
    target_actor: Optional[str] = None  # short_name
    target_zone: Optional[str] = None
    intensity: Literal["low", "medium", "high"] = "medium"
    locality: Optional[str] = None
    intent_annotation: Optional[str] = None
    communication_mode: Optional[str] = None
    rationale: str = ""                  # LLM-provided justification (for logging)

    military_cost: float = 0.0
    economic_cost: float = 0.0
    political_cost: float = 0.0

    @abstractmethod
    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        """Returns (is_valid, list_of_error_messages)."""
        pass

    @abstractmethod
    def get_expected_effects(self) -> Dict[str, str]:
        """Human-readable map of expected world state changes. For logging and display."""
        pass

    model_config = {"arbitrary_types_allowed": True}


def _capability_errors(action: BaseAction, state: "WorldState") -> List[str]:
    actor = state.get_actor(action.actor_id)
    if actor is None:
        return [f"Actor '{action.actor_id}' not found in world state."]
    if actor.capabilities is None:
        state.ensure_derived_state()
        actor = state.get_actor(action.actor_id)
    if actor is None or actor.capabilities is None:
        return ["Actor capability profile unavailable."]

    result = evaluate_action_constraints(action.action_type, actor.capabilities, state.pressures)
    errors = list(result.reasons)
    return errors


# ── Military Actions (8) ──────────────────────────────────────────────────────

class MobilizeAction(BaseAction):
    action_type: str = "mobilize"
    military_cost: float = 0.10
    economic_cost: float = 0.05

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if actor.military.readiness >= 0.9:
            errors.append("Readiness already at maximum (>= 0.9); mobilization not needed.")
        if actor.economic.gdp_strength < 0.2:
            errors.append("GDP strength too low (< 0.2) to sustain mobilization costs.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "military.readiness": "+0.15 to +0.25 (intensity-dependent)",
            "economic.gdp_strength": "-0.05 (sustained mobilization cost)",
            "signal": "Visible military escalation; increases adversary threat perception",
        }


class StrikeAction(BaseAction):
    action_type: str = "strike"
    military_cost: float = 0.20
    political_cost: float = 0.15

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None and self.target_zone is None:
            errors.append("Strike requires target_actor or target_zone.")
        if actor.military.readiness < 0.3:
            errors.append("Readiness too low (< 0.3) to execute strike.")
        if actor.military.conventional_forces < 0.2:
            errors.append("Conventional forces too depleted (< 0.2) to execute strike.")
        if self.target_actor is not None:
            allies = state.get_allies(self.actor_id)
            if self.target_actor in allies:
                errors.append(f"Cannot strike allied actor '{self.target_actor}'.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.military.conventional_forces": "-0.10 to -0.30 (intensity-dependent)",
            "actor.military.conventional_forces": "-0.05 to -0.15 (attrition)",
            "global_tension": "+0.10 to +0.20",
            "crisis_phase": "May escalate to 'crisis' or 'war'",
        }


class AdvanceAction(BaseAction):
    action_type: str = "advance"
    military_cost: float = 0.15

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_zone is None:
            errors.append("Advance requires target_zone.")
        if actor.military.logistics_capacity < 0.3:
            errors.append("Logistics capacity too low (< 0.3) to sustain advance.")
        if actor.military.readiness < 0.4:
            errors.append("Readiness too low (< 0.4) to execute advance.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "territory.contested_zones[target_zone]": "+0.10 to +0.25 (actor control increases)",
            "military.logistics_capacity": "-0.05 to -0.10",
            "global_tension": "+0.05 to +0.15",
        }


class WithdrawAction(BaseAction):
    action_type: str = "withdraw"
    military_cost: float = 0.05

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "military.readiness": "-0.05 to -0.10 (stand-down)",
            "global_tension": "-0.05 (de-escalatory signal)",
            "signal": "May be perceived as weakness or restraint depending on context",
        }


class BlockadeAction(BaseAction):
    action_type: str = "blockade"
    military_cost: float = 0.15
    economic_cost: float = 0.05

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if actor.military.naval_power < 0.3:
            errors.append("Naval power too low (< 0.3) to enforce blockade.")
        if self.target_actor is None and self.target_zone is None:
            errors.append("Blockade requires target_actor or target_zone.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.trade_openness": "-0.15 to -0.30",
            "systemic.global_shipping_disruption": "+0.10 to +0.20",
            "global_tension": "+0.08 to +0.15",
        }


class DefensivePostureAction(BaseAction):
    action_type: str = "defensive_posture"
    military_cost: float = 0.05

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "military.a2ad_effectiveness": "+0.05 to +0.15",
            "actor.current_posture": "→ 'defensive'",
            "signal": "De-escalatory; signals restraint while maintaining capability",
        }


class ProbeAction(BaseAction):
    action_type: str = "probe"
    military_cost: float = 0.05

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None and self.target_zone is None:
            errors.append("Probe requires target_actor or target_zone.")
        if actor.military.readiness < 0.2:
            errors.append("Readiness too low (< 0.2) to execute probe.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "actor.information_quality": "+0.03 to +0.08 (improved intelligence on target)",
            "global_tension": "+0.02 to +0.06",
            "signal": "Tests adversary resolve and reaction time without full commitment",
        }


class SignalResolveAction(BaseAction):
    action_type: str = "signal_resolve"
    political_cost: float = 0.02

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "relationships.deterrence_credibility": "+0.05 to +0.10 (allies gain confidence)",
            "signal": "Public commitment to defend interests; may deter adversary escalation",
        }


# ── Diplomatic Actions (6) ────────────────────────────────────────────────────

class NegotiateAction(BaseAction):
    action_type: str = "negotiate"
    political_cost: float = 0.05

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("Negotiate requires target_actor.")
        if actor.political.domestic_stability < 0.2:
            errors.append("Domestic stability too low (< 0.2) to pursue negotiations.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "relationships.trust_score": "+0.05 to +0.15",
            "global_tension": "-0.05 to -0.10",
            "signal": "Opens diplomatic channel; may reduce crisis phase escalation pressure",
        }


class TargetedSanctionAction(BaseAction):
    """
    Narrow, sector-specific sanctions on individuals, entities, or industries.
    Lower economic and political cost than comprehensive sanctions.
    Used as a graduated coercive tool before committing to full economic warfare.
    """
    action_type: str = "targeted_sanction"
    economic_cost: float = 0.03
    political_cost: float = 0.03

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("TargetedSanction requires target_actor.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.gdp_strength": "-0.03 to -0.07 (sector-limited)",
            "actor.economic.trade_openness": "-0.01 (minimal blowback)",
            "global_tension": "+0.02 to +0.05",
            "signal": "Graduated coercive signal; leaves room for further escalation",
        }


class ComprehensiveSanctionAction(BaseAction):
    """
    Broad sanctions regime covering finance, trade, and technology.
    High economic blowback for both parties; strong escalatory signal.
    Represents full economic warfare commitment — difficult to reverse.
    """
    action_type: str = "comprehensive_sanction"
    economic_cost: float = 0.10
    political_cost: float = 0.08

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("ComprehensiveSanction requires target_actor.")
        if actor.economic.gdp_strength < 0.3:
            errors.append(
                "GDP strength too low (< 0.3) to absorb comprehensive sanction blowback."
            )
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.gdp_strength": "-0.12 to -0.25 (broad economic damage)",
            "target.economic.trade_openness": "-0.15 to -0.25",
            "actor.economic.gdp_strength": "-0.06 to -0.12 (significant bilateral disruption)",
            "global_tension": "+0.06 to +0.12",
            "signal": "Full economic warfare; highly escalatory and hard to reverse",
        }


class FormAllianceAction(BaseAction):
    action_type: str = "form_alliance"
    political_cost: float = 0.10

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("FormAlliance requires target_actor.")
        if self.target_actor is not None:
            rel = state.get_relationship(self.actor_id, self.target_actor)
            if rel is not None and rel.relationship_type == "hostile":
                errors.append(f"Cannot form alliance with hostile actor '{self.target_actor}'.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "relationships.relationship_type": "→ 'ally' or 'partner'",
            "relationships.alliance_strength": "+0.15 to +0.30",
            "systemic.alliance_system_cohesion": "+0.05",
        }


class CondemnAction(BaseAction):
    action_type: str = "condemn"
    political_cost: float = 0.02

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("Condemn requires target_actor.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.political.international_standing": "-0.03 to -0.08",
            "relationships.trust_score": "-0.02 to -0.05",
            "signal": "Low-cost signaling; minimal escalatory risk",
        }


class IntelSharingAction(BaseAction):
    action_type: str = "intel_sharing"
    political_cost: float = 0.03

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("IntelSharing requires target_actor.")
        if self.target_actor is not None:
            rel = state.get_relationship(self.actor_id, self.target_actor)
            if rel is not None and rel.relationship_type in ("adversary", "hostile"):
                errors.append(
                    f"Cannot share intelligence with adversarial/hostile actor '{self.target_actor}'."
                )
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.information_quality": "+0.05 to +0.12",
            "relationships.trust_score": "+0.05 to +0.10",
            "relationships.alliance_strength": "+0.03",
        }


class BackChannelAction(BaseAction):
    action_type: str = "back_channel"
    political_cost: float = 0.02

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("BackChannel requires target_actor.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "relationships.trust_score": "+0.02 to +0.06",
            "global_tension": "-0.02 to -0.05",
            "signal": "Private communication; does not generate public escalatory signal",
        }


# ── Economic Actions (3) ──────────────────────────────────────────────────────

class EmbargoAction(BaseAction):
    action_type: str = "embargo"
    economic_cost: float = 0.08

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("Embargo requires target_actor.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.trade_openness": "-0.15 to -0.25",
            "target.economic.gdp_strength": "-0.08 to -0.18",
            "actor.economic.gdp_strength": "-0.04 to -0.08 (bilateral disruption)",
            "systemic.global_shipping_disruption": "+0.05",
        }


class ForeignAidAction(BaseAction):
    action_type: str = "foreign_aid"
    economic_cost: float = 0.05

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("ForeignAid requires target_actor.")
        if actor.economic.foreign_reserves < 0.2:
            errors.append("Foreign reserves too low (< 0.2) to provide aid.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.gdp_strength": "+0.03 to +0.08",
            "relationships.trust_score": "+0.05 to +0.10",
            "relationships.alliance_strength": "+0.05",
        }


class CutSupplyAction(BaseAction):
    action_type: str = "cut_supply"
    economic_cost: float = 0.04

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("CutSupply requires target_actor.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.industrial_capacity": "-0.05 to -0.15",
            "systemic.semiconductor_supply_chain_integrity": "-0.05 to -0.12 (if Taiwan-related)",
            "global_tension": "+0.03 to +0.07",
        }


class TechnologyRestrictionAction(BaseAction):
    """
    Export controls and technology transfer restrictions targeting adversary
    industrial and military capability. Primary instrument: semiconductor and
    dual-use technology denial. In the Taiwan Strait context this is the
    US chip export control lever (TSMC access, EDA tools, advanced nodes).
    Hits industrial capacity hard; actor absorbs trade blowback.
    """
    action_type: str = "technology_restriction"
    economic_cost: float = 0.06
    political_cost: float = 0.04

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("TechnologyRestriction requires target_actor.")
        if actor.economic.industrial_capacity < 0.4:
            errors.append(
                "Industrial capacity too low (< 0.4) to impose meaningful technology restrictions."
            )
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.industrial_capacity": "-0.10 to -0.22 (long-term capability denial)",
            "target.military.readiness": "-0.03 to -0.07 (dual-use tech denial)",
            "actor.economic.trade_openness": "-0.04 (supply chain reorganization costs)",
            "systemic.semiconductor_supply_chain_integrity": "-0.06 to -0.12",
            "global_tension": "+0.04 to +0.08",
            "signal": "Long-duration economic coercion; harder to reverse than sanctions",
        }


# ── Inaction Actions (2) ──────────────────────────────────────────────────────
# Collapsed from 4 to 2 — delay_commitment and wait_and_observe were semantically
# indistinguishable from hold_position and added noise to BCI measurement.

class HoldPositionAction(BaseAction):
    action_type: str = "hold_position"

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "world_state": "No change (deliberate inaction)",
            "signal": "Ambiguous — may be read as patience, indecision, or restraint",
        }


class MonitorAction(BaseAction):
    action_type: str = "monitor"

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "actor.information_quality": "+0.01 to +0.03 (passive intelligence accumulation)",
            "signal": "Non-escalatory; gathers information without commitment",
        }


# ── Information / Cyber Actions (3) ──────────────────────────────────────────

class PropagandaAction(BaseAction):
    action_type: str = "propaganda"
    political_cost: float = 0.03

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "actor.political.domestic_stability": "+0.03 to +0.06 (domestic narrative control)",
            "target.political.international_standing": "-0.03 to -0.06",
            "signal": "Information operation; affects perception without kinetic escalation",
        }


class PartialCoercionAction(BaseAction):
    action_type: str = "partial_coercion"
    economic_cost: float = 0.04
    military_cost: float = 0.03

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("PartialCoercion requires target_actor.")
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.political.regime_legitimacy": "-0.03 to -0.08",
            "target.economic.gdp_strength": "-0.03 to -0.06",
            "global_tension": "+0.04 to +0.10",
            "signal": "Gray-zone pressure combining economic and military signaling",
        }


class CyberOperationAction(BaseAction):
    """
    Offensive cyber operation targeting adversary infrastructure, C2 systems,
    or financial networks. Plausibly deniable — does not generate a public
    escalatory signal the way kinetic actions do. Key PRC and US instrument
    in early crisis stages. Requires high information quality as proxy for
    developed cyber capability (no dedicated cyber_capability field yet).
    """
    action_type: str = "cyber_operation"
    military_cost: float = 0.04
    political_cost: float = 0.03

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if self.target_actor is None:
            errors.append("CyberOperation requires target_actor.")
        if actor.information_quality < 0.50:
            errors.append(
                "Information quality too low (< 0.50) to execute sophisticated cyber operation."
            )
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "target.economic.industrial_capacity": "-0.04 to -0.10 (infrastructure disruption)",
            "target.information_quality": "-0.03 to -0.07 (C2/sensor degradation)",
            "global_tension": "+0.01 to +0.04 (deniable — low public escalation signal)",
            "signal": "Gray-zone; attribution ambiguous, escalation risk is managed",
        }


# ── Nuclear Actions (1) ───────────────────────────────────────────────────────

class NuclearSignalAction(BaseAction):
    """
    Nuclear posture escalation signal — not use, but credible threat.
    Examples: raising alert levels, dispersing nuclear assets, public
    statements about nuclear doctrine, moving ballistic missile submarines.
    Central to Waltzian deterrence logic — the threat that makes war unthinkable.
    Dramatically increases tension and adversary threat perception.
    Requires meaningful nuclear capability to be credible.
    """
    action_type: str = "nuclear_signal"
    military_cost: float = 0.08
    political_cost: float = 0.12

    def is_valid(self, state: "WorldState") -> Tuple[bool, List[str]]:
        errors = _capability_errors(self, state)
        actor = state.get_actor(self.actor_id)
        if actor is None:
            errors.append(f"Actor '{self.actor_id}' not found in world state.")
            return False, errors
        if actor.military.nuclear_capability < 0.30:
            errors.append(
                "Nuclear capability too low (< 0.30) to issue credible nuclear signal. "
                "Actor lacks a meaningful nuclear deterrent."
            )
        return len(errors) == 0, errors

    def get_expected_effects(self) -> Dict[str, str]:
        return {
            "relationships.deterrence_credibility": "+0.10 to +0.20 (allies reassured, adversary warned)",
            "relationships.threat_perception": "+0.15 to +0.25 (adversary perceives existential risk)",
            "global_tension": "+0.08 to +0.18 (major escalatory signal)",
            "crisis_phase": "High risk of triggering crisis → war transition",
            "signal": "Existential coercion; crosses a threshold — adversary must respond or back down",
        }


# ── Registry + Parser ─────────────────────────────────────────────────────────

ACTION_REGISTRY: Dict[str, type] = {
    # Military (8)
    "mobilize": MobilizeAction,
    "strike": StrikeAction,
    "advance": AdvanceAction,
    "withdraw": WithdrawAction,
    "blockade": BlockadeAction,
    "defensive_posture": DefensivePostureAction,
    "probe": ProbeAction,
    "signal_resolve": SignalResolveAction,
    # Diplomatic (7)
    "negotiate": NegotiateAction,
    "targeted_sanction": TargetedSanctionAction,
    "comprehensive_sanction": ComprehensiveSanctionAction,
    "form_alliance": FormAllianceAction,
    "condemn": CondemnAction,
    "intel_sharing": IntelSharingAction,
    "back_channel": BackChannelAction,
    # Economic (4)
    "embargo": EmbargoAction,
    "foreign_aid": ForeignAidAction,
    "cut_supply": CutSupplyAction,
    "technology_restriction": TechnologyRestrictionAction,
    # Information / Cyber (3)
    "propaganda": PropagandaAction,
    "partial_coercion": PartialCoercionAction,
    "cyber_operation": CyberOperationAction,
    # Nuclear (1)
    "nuclear_signal": NuclearSignalAction,
    # Inaction (2)
    "hold_position": HoldPositionAction,
    "monitor": MonitorAction,
}


def parse_action_from_dict(data: Dict[str, Any]) -> BaseAction:
    """
    Parse a raw dict (from LLM JSON output) into a typed action.
    Raises ValueError if action_type is unknown.
    """
    action_type = data.get("action_type")
    if not action_type or action_type not in ACTION_REGISTRY:
        valid = list(ACTION_REGISTRY.keys())
        raise ValueError(
            f"Unknown action_type: '{action_type}'. "
            f"Valid types: {valid}"
        )
    return ACTION_REGISTRY[action_type](**data)


def get_available_actions_for(actor_id: str, state: "WorldState") -> List[str]:
    """
    Return list of action_type strings that are currently valid for this actor.
    Used to populate the action menu in LLM decision prompts.

    Uses sentinel target values so that target-requirement checks pass and only
    actor-capability preconditions (readiness, GDP, naval power, etc.) determine
    availability. The sentinel won't match any real actor, so relationship-based
    checks (e.g. "can't strike allies") correctly skip rather than false-trigger.
    """
    state.ensure_derived_state()
    _SENTINEL = "__availability_check__"
    available = []
    for action_type, action_class in ACTION_REGISTRY.items():
        try:
            instance = action_class(
                action_type=action_type,
                actor_id=actor_id,
                target_actor=_SENTINEL,
                target_zone=_SENTINEL,
                rationale="",
            )
            valid, _ = instance.is_valid(state)
            if valid:
                available.append(action_type)
        except Exception:
            pass
    return available
