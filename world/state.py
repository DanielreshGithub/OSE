"""
World state data models for the Omni-Simulation Engine.

All resource values are normalized floats in [0.0, 1.0]. Pydantic enforces
these bounds at instantiation — any mutation that drifts a value out of range
will raise ValidationError. LLM actors never see raw floats; they receive
qualitative bands (HIGH/MEDIUM/LOW) derived from these values via the
perception filter in actors/llm_actor.py.
"""
from __future__ import annotations
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

from world.capabilities import CapabilityVector
from world.pressures import PressureState, empty_pressure_state


# ── Resource Models ──────────────────────────────────────────────────────────

class MilitaryResources(BaseModel):
    conventional_forces: float = Field(ge=0.0, le=1.0)
    naval_power: float = Field(ge=0.0, le=1.0)
    air_superiority: float = Field(ge=0.0, le=1.0)
    nuclear_capability: float = Field(ge=0.0, le=1.0, description="0=none, 1=full strategic")
    logistics_capacity: float = Field(ge=0.0, le=1.0, description="Sustainment and operational reach")
    readiness: float = Field(ge=0.0, le=1.0, description="Current mobilization state")
    amphibious_capacity: float = Field(ge=0.0, le=1.0, description="Capacity to execute opposed amphibious landings")
    a2ad_effectiveness: float = Field(ge=0.0, le=1.0, description="Ability to deny adversary access to theater")


class EconomicResources(BaseModel):
    gdp_strength: float = Field(ge=0.0, le=1.0)
    foreign_reserves: float = Field(ge=0.0, le=1.0)
    energy_independence: float = Field(ge=0.0, le=1.0)
    trade_openness: float = Field(ge=0.0, le=1.0, description="Vulnerability to trade disruption")
    industrial_capacity: float = Field(ge=0.0, le=1.0, description="Defense-industrial base")
    semiconductor_dependency: float = Field(ge=0.0, le=1.0, description="Reliance on Taiwan semiconductor supply")


class PoliticalResources(BaseModel):
    domestic_stability: float = Field(ge=0.0, le=1.0)
    regime_legitimacy: float = Field(ge=0.0, le=1.0)
    international_standing: float = Field(ge=0.0, le=1.0)
    decision_unity: float = Field(ge=0.0, le=1.0, description="Coherence of leadership decision-making")
    casualty_tolerance: float = Field(ge=0.0, le=1.0, description="Public/elite tolerance for military casualties")


class TerritoryControl(BaseModel):
    core_territory: float = Field(ge=0.0, le=1.0, description="Control of home territory")
    contested_zones: Dict[str, float] = Field(
        default_factory=dict,
        description="zone_id -> control percentage (0=adversary, 1=self)"
    )
    strategic_straits: Dict[str, float] = Field(
        default_factory=dict,
        description="strait_id -> access percentage"
    )


# ── Relationship Model ────────────────────────────────────────────────────────

RelationshipType = Literal[
    "ally", "partner", "neutral", "competitor", "adversary", "hostile"
]


class BilateralRelationship(BaseModel):
    from_actor: str  # short_name
    to_actor: str    # short_name
    relationship_type: RelationshipType
    trust_score: float = Field(ge=0.0, le=1.0)
    alliance_strength: float = Field(ge=0.0, le=1.0, description="Formal commitment depth")
    trade_dependency: float = Field(ge=0.0, le=1.0, description="Economic interdependence")
    threat_perception: float = Field(ge=0.0, le=1.0, description="How threatening from_actor views to_actor")
    deterrence_credibility: float = Field(ge=0.0, le=1.0, description="from_actor's belief that to_actor will honor commitments")
    last_updated_turn: int = 0


# ── Actor Model ───────────────────────────────────────────────────────────────

ActorType = Literal["state", "alliance", "international_org", "non_state"]

CrisisPhase = Literal["peacetime", "tension", "crisis", "war", "post_conflict"]


class RedLine(BaseModel):
    description: str
    trigger_condition: str  # Natural language — used in LLM prompt
    if_crossed: str         # Expected response category


class Actor(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    short_name: str  # e.g. "USA", "PRC", "TWN", "JPN"
    actor_type: ActorType = "state"

    # Resources
    military: MilitaryResources
    economic: EconomicResources
    political: PoliticalResources
    territory: TerritoryControl

    # Strategic properties — fed into doctrine prompts
    goals: List[str]           # Priority-ordered list
    red_lines: List[RedLine]
    ideology: str              # Free text — core worldview
    strategic_culture: str     # How this actor characteristically approaches decisions
    decision_style: str        # e.g. "calculated, patient" / "reactive, risk-averse"

    # Deep behavioral grounding — constrain LLM toward real-world patterns
    historical_precedents: str = ""  # How this actor behaved in analogous past crises
    institutional_constraints: str = ""  # Actual decision-making machinery and procedural limits
    cognitive_patterns: str = ""  # Documented biases, blind spots, cultural heuristics
    war_aversion: str = ""  # Why war is specifically catastrophic for THIS actor
    military_doctrine_narrative: str = ""  # Revealed operational doctrine — how this actor actually fights, anchored in observed historical campaigns

    # Perception and intel
    information_quality: float = Field(
        default=0.75, ge=0.0, le=1.0,
        description="Accuracy of this actor's intelligence. Controls perception filter noise."
    )
    capabilities: Optional[CapabilityVector] = None
    perceived_threats: Dict[str, float] = Field(
        default_factory=dict,
        description="short_name -> threat level (0-1) as perceived by this actor"
    )

    # Turn state — reset each turn
    is_active: bool = True
    actions_this_turn: List[str] = Field(default_factory=list)
    current_posture: Literal["cautious", "opportunistic", "escalatory", "defensive", "signaling_restraint"] = "cautious"


# ── Spatial Layer (Phase A) ───────────────────────────────────────────────────

UnitType = Literal[
    "csg",                  # Carrier Strike Group
    "surface_action_group", # Multi-ship surface combatant group
    "destroyer",            # Single major surface combatant
    "frigate",
    "corvette",
    "submarine",
    "ssbn",                 # Ballistic missile submarine
    "amphibious_group",     # LHD/LPD task group
    "air_wing",             # Carrier air wing
    "fighter_squadron",
    "bomber_squadron",
    "isr_squadron",         # ISR / patrol aircraft
    "missile_brigade",      # Land-based ballistic or cruise missile unit
    "sam_battery",          # Surface-to-air missile battery
    "coastal_defense",      # Mobile anti-ship missile / artillery battalion
    "infantry_brigade",
    "marine_meu",           # Marine Expeditionary Unit
    "sof_detachment",       # Special Operations Forces
    "cyber_unit",
]


UnitState = Literal[
    "standby",        # In home port / at fixed garrison; not deployed
    "transit",        # Underway toward a destination
    "on_station",     # Arrived at deployment location; holding
    "in_engagement",  # Actively engaged in combat
    "damaged",        # Combat-degraded; reduced effectiveness
    "destroyed",      # Out of action
]


class Unit(BaseModel):
    """A platform-level military unit with a real-world position.

    Phase A: Unit is tracked data only. Resolver does not yet move units
    (that lands in Phase B). Positions update via dedicated movement actions
    in Phase B; for now positions are static from initial roster.
    """
    unit_id: str
    owner: str                                  # short_name (USA/PRC/TWN/JPN)
    unit_type: UnitType
    platform_class: str                         # e.g. "Nimitz (CVN-71)", "Type 055"
    home_port: Optional[str] = None             # named_locations key
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    speed_kts: float = Field(default=20.0, ge=0.0, le=2000.0,
                             description="Sustained transit speed. Subsonic for ships, "
                                         "Mach-converted for aircraft on positioning.")
    range_km_per_turn: float = Field(default=0.0, ge=0.0,
                                     description="Max km per turn at sustained speed. "
                                                 "Computed from speed_kts × turn_duration_hours × 1.852.")
    state: UnitState = "standby"
    destination_lat: Optional[float] = None
    destination_lon: Optional[float] = None
    composition: Dict[str, Any] = Field(default_factory=dict,
                                        description="Free-form: escorts, air wing, embarked forces, weapons load")
    source: str = ""
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"

    model_config = {"extra": "forbid"}


class NamedLocation(BaseModel):
    """A referenceable geographic point used by actions and event templates."""
    name: str
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    location_type: Literal[
        "naval_base", "air_base", "joint_base",
        "strait", "channel", "contested_feature",
        "capital", "civilian_port",
    ]
    description: str = ""

    model_config = {"extra": "forbid"}


# ── Systemic Indicators ───────────────────────────────────────────────────────

class SystemicIndicators(BaseModel):
    """Global indicators that are not actor-specific."""
    semiconductor_supply_chain_integrity: float = Field(
        ge=0.0, le=1.0,
        description="Global semiconductor supply chain health. Degrades under Taiwan Strait crisis."
    )
    global_shipping_disruption: float = Field(
        ge=0.0, le=1.0,
        description="Degree of disruption to global shipping lanes."
    )
    energy_market_volatility: float = Field(
        ge=0.0, le=1.0,
        description="Energy price instability caused by crisis."
    )
    alliance_system_cohesion: float = Field(
        ge=0.0, le=1.0,
        description="Health of US-led alliance system. Degrades if commitments are not honored."
    )


# ── World State ───────────────────────────────────────────────────────────────

class WorldState(BaseModel):
    scenario_id: str
    scenario_name: str
    turn: int = 0
    max_turns: int = 15

    actors: Dict[str, Actor]                    # short_name -> Actor
    relationships: List[BilateralRelationship]
    systemic: SystemicIndicators
    pressures: PressureState = Field(default_factory=empty_pressure_state)

    # ── Spatial layer (Phase A: tracked but not yet acted on by resolver) ────
    units: Dict[str, Unit] = Field(
        default_factory=dict,
        description="Platform-level units keyed by unit_id. Phase A: data-only; "
                    "movement mechanics land in Phase B.",
    )
    named_locations: Dict[str, NamedLocation] = Field(
        default_factory=dict,
        description="Referenceable geographic points (bases, straits, features) "
                    "keyed by lowercase name.",
    )

    global_tension: float = Field(ge=0.0, le=1.0, description="Aggregate system tension")
    active_conflicts: List[str] = Field(default_factory=list, description="Active conflict zone IDs")
    crisis_phase: CrisisPhase = "peacetime"
    random_seed: int = 0

    # History — typed as Any to avoid circular import with world/events.py
    # At runtime these hold List[TurnLog] and List[DecisionRecord] respectively
    turn_logs: List[Any] = Field(default_factory=list)
    decision_history: List[Any] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

    # ── Query helpers ─────────────────────────────────────────────────────────

    def get_actor(self, short_name: str) -> Optional[Actor]:
        return self.actors.get(short_name)

    def get_relationship(self, from_actor: str, to_actor: str) -> Optional[BilateralRelationship]:
        for r in self.relationships:
            if r.from_actor == from_actor and r.to_actor == to_actor:
                return r
        return None

    def get_allies(self, short_name: str, min_strength: float = 0.5) -> List[str]:
        return [
            r.to_actor for r in self.relationships
            if r.from_actor == short_name
            and r.relationship_type in ("ally", "partner")
            and r.alliance_strength >= min_strength
        ]

    def get_adversaries(self, short_name: str) -> List[str]:
        return [
            r.to_actor for r in self.relationships
            if r.from_actor == short_name
            and r.relationship_type in ("adversary", "hostile")
        ]

    def clamp_all_resources(self) -> "WorldState":
        """
        After any world state mutation, call this to ensure all floats remain in [0, 1].
        Returns self for chaining.
        """
        for actor in self.actors.values():
            for resource_group in [actor.military, actor.economic, actor.political]:
                for field_name in resource_group.__class__.model_fields:
                    val = getattr(resource_group, field_name)
                    if isinstance(val, float):
                        setattr(resource_group, field_name, max(0.0, min(1.0, val)))
            if actor.capabilities is not None:
                actor.capabilities.clamp()
        self.global_tension = max(0.0, min(1.0, self.global_tension))
        self.pressures.clamp()
        return self

    def ensure_derived_state(self) -> "WorldState":
        """
        Populate any additive derived state required by the open-ended engine.
        """
        from engine.capabilities import build_actor_capabilities

        for actor in self.actors.values():
            actor.capabilities = build_actor_capabilities(actor, self)
        if not self.pressures.scenario_id:
            self.pressures.scenario_id = self.scenario_id
        self.pressures.turn = self.turn
        return self.clamp_all_resources()

    model_config = {"arbitrary_types_allowed": True}
