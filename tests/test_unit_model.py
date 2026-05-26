"""Tests for the Phase A spatial layer — Unit + NamedLocation models and
their integration with the Taiwan Strait scenario.
"""
from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from pydantic import ValidationError

from world.state import Unit, NamedLocation, WorldState
from scenarios.taiwan_strait import TaiwanStraitScenario


class UnitModelTests(unittest.TestCase):
    def test_unit_round_trip(self):
        u = Unit(
            unit_id="USA_CSG_X",
            owner="USA",
            unit_type="csg",
            platform_class="Nimitz",
            lat=35.29,
            lon=139.66,
            speed_kts=30,
            range_km_per_turn=1300,
            state="standby",
        )
        dumped = u.model_dump()
        restored = Unit(**dumped)
        self.assertEqual(restored.unit_id, "USA_CSG_X")
        self.assertEqual(restored.owner, "USA")
        self.assertEqual(restored.state, "standby")

    def test_unit_rejects_out_of_range_latitude(self):
        with self.assertRaises(ValidationError):
            Unit(
                unit_id="X", owner="USA", unit_type="csg",
                platform_class="X", lat=91.0, lon=0.0,
            )

    def test_unit_rejects_unknown_state(self):
        with self.assertRaises(ValidationError):
            Unit(
                unit_id="X", owner="USA", unit_type="csg",
                platform_class="X", lat=0.0, lon=0.0, state="warping",
            )

    def test_unit_rejects_unknown_unit_type(self):
        with self.assertRaises(ValidationError):
            Unit(
                unit_id="X", owner="USA", unit_type="death_star",
                platform_class="X", lat=0.0, lon=0.0,
            )


class NamedLocationModelTests(unittest.TestCase):
    def test_named_location_round_trip(self):
        loc = NamedLocation(
            name="yokosuka", lat=35.29, lon=139.66,
            location_type="naval_base", description="x",
        )
        restored = NamedLocation(**loc.model_dump())
        self.assertEqual(restored.name, "yokosuka")
        self.assertEqual(restored.location_type, "naval_base")


class ScenarioIntegrationTests(unittest.TestCase):
    def test_scenario_loads_units_and_locations(self):
        state = TaiwanStraitScenario(seed=0).initialize()
        self.assertGreater(len(state.units), 30,
                           "expected substantial unit roster, got too few")
        self.assertGreater(len(state.named_locations), 20,
                           "expected substantial named-location roster, got too few")

    def test_all_units_owned_by_a_scenario_actor(self):
        state = TaiwanStraitScenario(seed=0).initialize()
        scenario_actors = set(state.actors.keys())
        for unit_id, unit in state.units.items():
            with self.subTest(unit_id=unit_id):
                self.assertIn(
                    unit.owner, scenario_actors,
                    f"{unit_id} has owner={unit.owner!r} not in scenario actors",
                )

    def test_all_unit_home_ports_resolve_to_locations(self):
        state = TaiwanStraitScenario(seed=0).initialize()
        for unit_id, unit in state.units.items():
            if unit.home_port is None:
                continue
            with self.subTest(unit_id=unit_id):
                self.assertIn(
                    unit.home_port, state.named_locations,
                    f"{unit_id}.home_port={unit.home_port!r} not in named_locations",
                )

    def test_each_actor_has_units(self):
        state = TaiwanStraitScenario(seed=0).initialize()
        owners = {u.owner for u in state.units.values()}
        for actor in ("USA", "PRC", "TWN", "JPN"):
            self.assertIn(actor, owners, f"no units owned by {actor}")

    def test_snapshot_serializes_units(self):
        """WorldState.model_dump() round-trips units cleanly — required for
        SQLite logging via the engine snapshot pipeline."""
        state = TaiwanStraitScenario(seed=0).initialize()
        dumped = state.model_dump()
        self.assertIn("units", dumped)
        self.assertIsInstance(dumped["units"], dict)
        self.assertGreater(len(dumped["units"]), 0)
        # Pick any unit and check its structure
        any_unit = next(iter(dumped["units"].values()))
        self.assertIn("lat", any_unit)
        self.assertIn("lon", any_unit)
        self.assertIn("owner", any_unit)


if __name__ == "__main__":
    unittest.main()
