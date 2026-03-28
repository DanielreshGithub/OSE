# OSE Scaffolding Build Prompt

## Mission

Build the foundational scaffolding for the **Omni-Simulation Engine (OSE)** — a Python research framework for LLM-driven geopolitical conflict simulation. Your task is to implement Phases 1 and 2 of the build plan: the world state data models, the action space, and the project configuration. Do not build anything beyond what is specified here.

---

## Project Context

OSE is a modular simulation in which LLM agents play the role of state-level decision-makers in a geopolitical crisis. Actors receive a filtered, noisy view of a shared world state, reason through a prescribed decision doctrine, and select typed actions from a defined schema. A rule-based validator sits between LLM output and world state mutation — the LLM never touches world state directly.

The first scenario is the Taiwan Strait 2026 crisis with four actors: USA, PRC, TWN (Taiwan), JPN (Japan).

This is a research instrument, not a game. Every design decision should favor inspectability, reproducibility, and explicit structure over cleverness or abstraction.

---

## Tech Stack

- **Python 3.11+**
- **Pydantic v2** — all data models; strict typing; `Field(ge=0.0, le=1.0)` constraints on resource floats
- **uv** — dependency management
- **No LLM calls in this phase** — the actor and engine layers come later

---

## Directory Structure to Create

```
ose/
├── pyproject.toml
├── .env.example
├── .gitignore
├── world/
│   ├── __init__.py
│   ├── state.py
│   ├── events.py
│   └── graph.py
├── actors/
│   ├── __init__.py
│   └── prompts/
│       └── .gitkeep
├── engine/
│   ├── __init__.py
│   └── actions.py
├── scenarios/
│   └── __init__.py
├── cli/
│   └── __init__.py
├── logs/
│   └── __init__.py
├── scoring/
│   └── __init__.py
└── experiments/
    └── __init__.py
```

---

## File Specifications

### `pyproject.toml`

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "ose"
version = "0.1.0"
description = "Omni-Simulation Engine — LLM-driven geopolitical conflict simulation research framework"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "pydantic>=2.0.0",
    "rich>=13.0.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
graph = ["networkx>=3.0"]
dev = ["pytest>=8.0.0", "pytest-asyncio>=0.23.0"]

[tool.hatch.build.targets.wheel]
packages = ["world", "actors", "engine", "scenarios", "cli", "logs", "scoring", "experiments"]
```

### `.env.example`

```
ANTHROPIC_API_KEY=your_key_here
OSE_LOG_DIR=logs/runs
OSE_DEFAULT_TURNS=15
OSE_DEFAULT_TEMPERATURE=0
```

### `.gitignore`

Standard Python gitignore. Also ignore: `.env`, `logs/runs/`, `*.db`, `__pycache__/`, `.pytest_cache/`, `dist/`, `.venv/`

---

### `world/state.py`

This is the most important file. Build it with extreme care. Every field matters.

**Design rules:**
- All resource values are floats in `[0.0, 1.0]`. Use `Field(ge=0.0, le=1.0)` on every resource float. Pydantic will raise `ValidationError` if anything drifts out of range — this is intentional and load-bearing.
- Use `from __future__ import annotations` for forward references.
- Use `Literal` types for categorical fields.
- All models inherit from `pydantic.BaseModel`.

```python
from __future__ import annotations
from typing import Dict, List, Optional, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid


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

    # Perception and intel
    information_quality: float = Field(
        default=0.75, ge=0.0, le=1.0,
        description="Accuracy of this actor's intelligence. Controls perception filter noise."
    )
    perceived_threats: Dict[str, float] = Field(
        default_factory=dict,
        description="short_name -> threat level (0-1) as perceived by this actor"
    )

    # Turn state — reset each turn
    is_active: bool = True
    actions_this_turn: List[str] = Field(default_factory=list)
    current_posture: Literal["cautious", "opportunistic", "escalatory", "defensive", "signaling_restraint"] = "cautious"


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

    global_tension: float = Field(ge=0.0, le=1.0, description="Aggregate system tension")
    active_conflicts: List[str] = Field(default_factory=list, description="Active conflict zone IDs")
    crisis_phase: CrisisPhase = "peacetime"

    # History
    turn_logs: List["TurnLog"] = Field(default_factory=list)
    decision_history: List["DecisionRecord"] = Field(default_factory=list)

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
                for field_name in resource_group.model_fields:
                    val = getattr(resource_group, field_name)
                    if isinstance(val, float):
                        setattr(resource_group, field_name, max(0.0, min(1.0, val)))
        self.global_tension = max(0.0, min(1.0, self.global_tension))
        return self

    model_config = {"arbitrary_types_allowed": True}
```

---

### `world/events.py`

```python
from __future__ import annotations
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field
from datetime import datetime
import uuid

EventCategory = Literal[
    "military", "diplomatic", "economic", "information", "natural", "cascade", "injected"
]

ValidationResult = Literal["valid", "invalid", "retry_valid", "retry_invalid", "skipped"]


class GlobalEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    turn: int
    category: EventCategory
    description: str
    source: Literal["system", "actor", "cascade", "injected"]
    caused_by_actor: Optional[str] = None   # short_name
    affected_actors: List[str] = Field(default_factory=list)
    world_state_delta: Dict[str, Any] = Field(
        default_factory=dict,
        description="Human-readable description of what changed"
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class DecisionRecord(BaseModel):
    """Complete log of one actor's decision in one turn."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    turn: int
    actor_short_name: str
    doctrine_condition: str   # "realist" | "liberal" | "org_process" | "baseline"
    run_id: str

    # Prompt inputs (stored for replay)
    system_prompt: str
    perception_block: str

    # LLM outputs
    reasoning_trace: str          # Full chain-of-thought / rationale schema output
    raw_llm_response: str         # Unparsed LLM response
    parsed_action: Optional[Dict[str, Any]] = None

    # Validation
    validation_result: ValidationResult
    validation_errors: List[str] = Field(default_factory=list)
    retry_count: int = 0
    final_applied: bool = False

    # Scoring (populated by fidelity scorer after the fact)
    doctrine_language_score: Optional[float] = None   # 0-1
    doctrine_logic_score: Optional[float] = None       # 0-1
    doctrine_consistent_decision: Optional[bool] = None
    contamination_flag: Optional[bool] = None

    # Crisis phase at time of decision (for pressure robustness analysis)
    crisis_phase_at_decision: str = "peacetime"

    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TurnLog(BaseModel):
    run_id: str
    turn: int
    doctrine_condition: str
    crisis_phase: str
    global_tension: float
    events_this_turn: List[GlobalEvent] = Field(default_factory=list)
    decisions: List[DecisionRecord] = Field(default_factory=list)
    cascade_events: List[GlobalEvent] = Field(default_factory=list)
    world_state_snapshot: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON serialization of WorldState at turn end"
    )
    terminal_condition_met: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class RunRecord(BaseModel):
    """Top-level record for one complete simulation run."""
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: str
    doctrine_condition: str
    run_number: int
    total_turns: int
    final_crisis_phase: str
    outcome_classification: Optional[str] = None   # deterrence_success | defense_success | frozen | failure
    final_global_tension: float
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    completed: bool = False
```

---

### `world/graph.py`

```python
from __future__ import annotations
from typing import Dict, List, Optional, Tuple
from world.state import BilateralRelationship, WorldState


class RelationshipGraph:
    """
    Thin query wrapper over WorldState.relationships.
    Provides named query methods without requiring NetworkX as a hard dependency.
    NetworkX export is available optionally for analysis.
    """

    def __init__(self, state: WorldState):
        self._state = state
        self._index: Dict[Tuple[str, str], BilateralRelationship] = {
            (r.from_actor, r.to_actor): r for r in state.relationships
        }

    def get(self, from_actor: str, to_actor: str) -> Optional[BilateralRelationship]:
        return self._index.get((from_actor, to_actor))

    def get_allies(self, actor: str, min_strength: float = 0.5) -> List[str]:
        return [
            r.to_actor for r in self._state.relationships
            if r.from_actor == actor
            and r.relationship_type in ("ally", "partner")
            and r.alliance_strength >= min_strength
        ]

    def get_adversaries(self, actor: str) -> List[str]:
        return [
            r.to_actor for r in self._state.relationships
            if r.from_actor == actor
            and r.relationship_type in ("adversary", "hostile")
        ]

    def get_threat_perception(self, perceiver: str, target: str) -> float:
        rel = self.get(perceiver, target)
        return rel.threat_perception if rel else 0.0

    def get_deterrence_credibility(self, believer: str, actor: str) -> float:
        """How credible does 'believer' find 'actor's' commitments?"""
        rel = self.get(believer, actor)
        return rel.deterrence_credibility if rel else 0.5

    def all_relationships_for(self, actor: str) -> List[BilateralRelationship]:
        return [r for r in self._state.relationships if r.from_actor == actor]

    def to_networkx(self):
        """Optional: export to NetworkX DiGraph for post-hoc analysis."""
        try:
            import networkx as nx
            G = nx.DiGraph()
            for r in self._state.relationships:
                G.add_edge(
                    r.from_actor, r.to_actor,
                    **r.model_dump(exclude={"from_actor", "to_actor"})
                )
            return G
        except ImportError:
            raise RuntimeError(
                "networkx not installed. Install with: uv add networkx"
            )
```

---

### `engine/actions.py`

Build all 23 typed action classes. Each must implement:
- `is_valid(state: WorldState) -> tuple[bool, List[str]]`
- `get_expected_effects() -> Dict[str, str]`
- Resource cost fields: `military_cost`, `economic_cost`, `political_cost` (all floats, default 0.0)

**Base class:**

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Literal, TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from world.state import WorldState


class BaseAction(BaseModel, ABC):
    action_type: str
    actor_id: str                        # short_name of acting actor
    target_actor: Optional[str] = None  # short_name
    target_zone: Optional[str] = None
    intensity: Literal["low", "medium", "high"] = "medium"
    rationale: str = ""                  # LLM-provided justification (for logging)

    military_cost: float = 0.0
    economic_cost: float = 0.0
    political_cost: float = 0.0

    @abstractmethod
    def is_valid(self, state: "WorldState") -> tuple[bool, List[str]]:
        """Returns (is_valid, list_of_error_messages)."""
        pass

    @abstractmethod
    def get_expected_effects(self) -> Dict[str, str]:
        """Human-readable map of expected world state changes. For logging and display."""
        pass
```

**Implement all 23 actions in the following categories. Each must be a separate class.**

**Military (8 actions):**

| Action class | `action_type` | Key validity rules | Cost fields |
|---|---|---|---|
| `MobilizeAction` | `"mobilize"` | actor exists; readiness < 0.9; econ.gdp_strength >= 0.2 | mil: 0.10, econ: 0.05 |
| `StrikeAction` | `"strike"` | target_actor or target_zone required; readiness >= 0.3; conventional_forces >= 0.2; cannot strike ally | mil: 0.20, pol: 0.15 |
| `AdvanceAction` | `"advance"` | target_zone required; logistics_capacity >= 0.3; readiness >= 0.4 | mil: 0.15 |
| `WithdrawAction` | `"withdraw"` | actor exists | mil: 0.05 |
| `BlockadeAction` | `"blockade"` | naval_power >= 0.3; target_actor or target_zone required | mil: 0.15, econ: 0.05 |
| `DefensivePostureAction` | `"defensive_posture"` | actor exists | mil: 0.05 |
| `ProbeAction` | `"probe"` | target_actor or target_zone required; readiness >= 0.2 | mil: 0.05 |
| `SignalResolveAction` | `"signal_resolve"` | actor exists | pol: 0.02 |

**Diplomatic (6 actions):**

| Action class | `action_type` | Key validity rules | Cost fields |
|---|---|---|---|
| `NegotiateAction` | `"negotiate"` | target_actor required; domestic_stability >= 0.2 | pol: 0.05 |
| `SanctionAction` | `"sanction"` | target_actor required | econ: 0.05, pol: 0.05 |
| `FormAllianceAction` | `"form_alliance"` | target_actor required; relationship_type != "hostile" | pol: 0.10 |
| `CondemnAction` | `"condemn"` | target_actor required | pol: 0.02 |
| `IntelSharingAction` | `"intel_sharing"` | target_actor required; relationship_type not adversary/hostile | pol: 0.03 |
| `BackChannelAction` | `"back_channel"` | target_actor required | pol: 0.02 |

**Economic (3 actions):**

| Action class | `action_type` | Key validity rules | Cost fields |
|---|---|---|---|
| `EmbargoAction` | `"embargo"` | target_actor required | econ: 0.08 |
| `ForeignAidAction` | `"foreign_aid"` | target_actor required; foreign_reserves >= 0.2 | econ: 0.05 |
| `CutSupplyAction` | `"cut_supply"` | target_actor required | econ: 0.04 |

**Inaction (4 actions — do not omit these):**

| Action class | `action_type` | Key validity rules | Cost fields |
|---|---|---|---|
| `HoldPositionAction` | `"hold_position"` | actor exists | all: 0.0 |
| `MonitorAction` | `"monitor"` | actor exists | all: 0.0 |
| `DelayCommitmentAction` | `"delay_commitment"` | actor exists | pol: 0.01 |
| `WaitAndObserveAction` | `"wait_and_observe"` | actor exists | all: 0.0 |

**Information (2 actions):**

| Action class | `action_type` | Key validity rules | Cost fields |
|---|---|---|---|
| `PropagandaAction` | `"propaganda"` | actor exists | pol: 0.03 |
| `PartialCoercionAction` | `"partial_coercion"` | target_actor required | econ: 0.04, mil: 0.03 |

**After all classes, add:**

```python
ACTION_REGISTRY: Dict[str, type] = {
    "mobilize": MobilizeAction,
    "strike": StrikeAction,
    "advance": AdvanceAction,
    "withdraw": WithdrawAction,
    "blockade": BlockadeAction,
    "defensive_posture": DefensivePostureAction,
    "probe": ProbeAction,
    "signal_resolve": SignalResolveAction,
    "negotiate": NegotiateAction,
    "sanction": SanctionAction,
    "form_alliance": FormAllianceAction,
    "condemn": CondemnAction,
    "intel_sharing": IntelSharingAction,
    "back_channel": BackChannelAction,
    "embargo": EmbargoAction,
    "foreign_aid": ForeignAidAction,
    "cut_supply": CutSupplyAction,
    "hold_position": HoldPositionAction,
    "monitor": MonitorAction,
    "delay_commitment": DelayCommitmentAction,
    "wait_and_observe": WaitAndObserveAction,
    "propaganda": PropagandaAction,
    "partial_coercion": PartialCoercionAction,
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
    """
    available = []
    for action_type, action_class in ACTION_REGISTRY.items():
        try:
            instance = action_class(
                action_type=action_type,
                actor_id=actor_id,
                rationale=""
            )
            valid, _ = instance.is_valid(state)
            if valid:
                available.append(action_type)
        except Exception:
            pass
    return available
```

---

## Architectural Constraints

**Do not violate these:**

1. **No LLM calls in this phase.** The `world/`, `engine/actions.py` files must have zero Anthropic SDK imports.

2. **All resource floats must use `Field(ge=0.0, le=1.0)`** — no exceptions. This is the primary sanity check on world state mutations.

3. **`is_valid()` must never call external services.** Pure function over world state.

4. **`ACTION_REGISTRY` must contain exactly 23 entries.** Count them.

5. **`parse_action_from_dict()` must raise `ValueError` on unknown action types**, not return `None` or fail silently.

6. **Do not add convenience methods or helpers beyond what is specified.** Scope strictly to what is listed.

7. **Every `__init__.py` file should be empty** except for a module docstring. No star imports.

---

## Verification

After building, verify with this test script (save as `test_scaffolding.py` at project root):

```python
"""Verify OSE scaffolding is correct."""
from world.state import (
    WorldState, Actor, MilitaryResources, EconomicResources,
    PoliticalResources, TerritoryControl, BilateralRelationship,
    SystemicIndicators, RedLine
)
from world.events import DecisionRecord, TurnLog, GlobalEvent, RunRecord
from world.graph import RelationshipGraph
from engine.actions import ACTION_REGISTRY, parse_action_from_dict, get_available_actions_for
from pydantic import ValidationError

# 1. Action registry has 23 entries
assert len(ACTION_REGISTRY) == 23, f"Expected 23 actions, got {len(ACTION_REGISTRY)}"

# 2. All actions instantiate without error
for name, cls in ACTION_REGISTRY.items():
    instance = cls(action_type=name, actor_id="USA", rationale="test")
    assert instance.action_type == name

# 3. Pydantic enforces float bounds
try:
    bad = MilitaryResources(
        conventional_forces=1.5, naval_power=0.5, air_superiority=0.5,
        nuclear_capability=0.0, logistics_capacity=0.5, readiness=0.5,
        amphibious_capacity=0.5, a2ad_effectiveness=0.5
    )
    assert False, "Should have raised ValidationError"
except ValidationError:
    pass

# 4. parse_action_from_dict raises on unknown type
try:
    parse_action_from_dict({"action_type": "nuke_everything", "actor_id": "USA", "rationale": ""})
    assert False, "Should have raised ValueError"
except ValueError:
    pass

# 5. WorldState initializes
mil = MilitaryResources(
    conventional_forces=0.85, naval_power=0.90, air_superiority=0.88,
    nuclear_capability=0.95, logistics_capacity=0.80, readiness=0.70,
    amphibious_capacity=0.30, a2ad_effectiveness=0.40
)
econ = EconomicResources(
    gdp_strength=0.80, foreign_reserves=0.75, energy_independence=0.65,
    trade_openness=0.70, industrial_capacity=0.85, semiconductor_dependency=0.40
)
pol = PoliticalResources(
    domestic_stability=0.70, regime_legitimacy=0.72, international_standing=0.85,
    decision_unity=0.75, casualty_tolerance=0.45
)
terr = TerritoryControl(
    core_territory=0.98,
    contested_zones={"taiwan_strait": 0.75},
    strategic_straits={"luzon_strait": 0.80}
)
actor = Actor(
    name="United States", short_name="USA", actor_type="state",
    military=mil, economic=econ, political=pol, territory=terr,
    goals=["Maintain regional stability", "Deter PRC aggression"],
    red_lines=[RedLine(
        description="PRC invasion of Taiwan",
        trigger_condition="PRC executes advance action targeting Taiwan core territory",
        if_crossed="Military intervention authorized"
    )],
    ideology="Liberal democratic hegemon committed to rules-based international order",
    strategic_culture="Prefers coalition-building, credible deterrence through forward presence",
    decision_style="Deliberate, process-driven, coalition-seeking before unilateral action",
    information_quality=0.82
)

systemic = SystemicIndicators(
    semiconductor_supply_chain_integrity=0.85,
    global_shipping_disruption=0.10,
    energy_market_volatility=0.20,
    alliance_system_cohesion=0.78
)

state = WorldState(
    scenario_id="taiwan_strait_2026",
    scenario_name="Taiwan Strait Crisis 2026",
    actors={"USA": actor},
    relationships=[],
    systemic=systemic,
    global_tension=0.55,
    crisis_phase="tension"
)
assert state.get_actor("USA") is not None
assert state.get_actor("PRC") is None

print("✓ All scaffolding checks passed.")
print(f"✓ ACTION_REGISTRY contains {len(ACTION_REGISTRY)} actions.")
print(f"✓ Pydantic validation enforces float bounds.")
print(f"✓ WorldState instantiates correctly.")
```

Run with: `python test_scaffolding.py`

Expected output:
```
✓ All scaffolding checks passed.
✓ ACTION_REGISTRY contains 23 actions.
✓ Pydantic validation enforces float bounds.
✓ WorldState instantiates correctly.
```

---

## What NOT to Build

Do not build:
- Any LLM actor logic (`actors/llm_actor.py`)
- Simulation loop (`engine/loop.py`)
- Scenario definitions (`scenarios/taiwan_strait.py`)
- CLI (`cli/run.py`)
- Logging (`logs/logger.py`)
- Scoring (`scoring/`)
- Experiment runner (`experiments/`)

These come in later phases. Build only what is specified above.
