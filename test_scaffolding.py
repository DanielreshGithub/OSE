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

# 1. Action registry has expected entries
assert len(ACTION_REGISTRY) == 25, f"Expected 25 actions, got {len(ACTION_REGISTRY)}"

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
