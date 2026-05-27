"""Tests for derived zone control from unit presence (Phase C).

Replaces static contested_zones scalar with a presence-derived value:
  - units inside a zone's bbox count toward owner share
  - empty zones leave existing scalar untouched (legacy compatibility)
  - destroyed units don't count
"""
from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from world.state import Unit, WorldState
from scenarios.taiwan_strait import TaiwanStraitScenario
from scenarios.data.zone_bboxes import zone_contains, ZONE_BBOXES


def _place_unit(state, unit_id, owner, lat, lon, state_val="on_station"):
    """Helper: drop a synthetic unit into the state at a specific position."""
    state.units[unit_id] = Unit(
        unit_id=unit_id,
        owner=owner,
        unit_type="destroyer",
        platform_class="synthetic",
        lat=lat, lon=lon,
        speed_kts=25,
        range_km_per_turn=1100,
        state=state_val,
    )


class ZoneBBoxTests(unittest.TestCase):
    def test_taiwan_strait_bbox_contains_known_point(self):
        # Taiwan Strait centerline (24.50, 119.50) should be inside taiwan_strait bbox.
        self.assertTrue(zone_contains("taiwan_strait", 24.50, 119.50))

    def test_taiwan_strait_bbox_excludes_yokosuka(self):
        # Yokosuka (35.29, 139.66) is way outside Taiwan Strait.
        self.assertFalse(zone_contains("taiwan_strait", 35.29, 139.66))

    def test_unknown_zone_returns_false(self):
        self.assertFalse(zone_contains("atlantis", 0.0, 0.0))


class DeriveContestedZonesTests(unittest.TestCase):
    def setUp(self):
        self.scenario = TaiwanStraitScenario(seed=0, year_horizon="2026")
        self.state = self.scenario.initialize()
        # Wipe existing roster so we can control composition for the test.
        self.state.units = {}

    def test_three_usa_one_prc_in_zone_yields_75_25(self):
        # Place 3 USA + 1 PRC units inside taiwan_strait bbox.
        bbox = ZONE_BBOXES["taiwan_strait"]
        # All inside: lat 24.0 lon 120.0 is centerline-ish
        _place_unit(self.state, "USA_1", "USA", 24.0, 120.0)
        _place_unit(self.state, "USA_2", "USA", 24.5, 119.5)
        _place_unit(self.state, "USA_3", "USA", 25.0, 120.5)
        _place_unit(self.state, "PRC_1", "PRC", 23.5, 120.0)
        self.state.derive_contested_zones()
        self.assertAlmostEqual(
            self.state.actors["USA"].territory.contested_zones["taiwan_strait"], 0.75, places=3
        )
        self.assertAlmostEqual(
            self.state.actors["PRC"].territory.contested_zones["taiwan_strait"], 0.25, places=3
        )

    def test_units_outside_bbox_dont_count(self):
        # USA unit at Yokosuka — far outside Taiwan Strait.
        _place_unit(self.state, "USA_1", "USA", 35.29, 139.66)
        # PRC unit inside Taiwan Strait.
        _place_unit(self.state, "PRC_1", "PRC", 24.0, 120.0)
        self.state.derive_contested_zones()
        # PRC gets 100% of taiwan_strait control.
        self.assertAlmostEqual(
            self.state.actors["PRC"].territory.contested_zones["taiwan_strait"], 1.0, places=3
        )
        # USA's contested_zones for taiwan_strait should be 0
        self.assertAlmostEqual(
            self.state.actors["USA"].territory.contested_zones.get("taiwan_strait", 0.0),
            0.0, places=3,
        )

    def test_destroyed_units_excluded(self):
        _place_unit(self.state, "USA_1", "USA", 24.0, 120.0, state_val="destroyed")
        _place_unit(self.state, "PRC_1", "PRC", 24.0, 120.0)
        self.state.derive_contested_zones()
        self.assertAlmostEqual(
            self.state.actors["PRC"].territory.contested_zones["taiwan_strait"], 1.0, places=3
        )

    def test_empty_zone_preserves_legacy_scalar(self):
        # Seed an explicit legacy value, place no units in taiwan_strait,
        # and confirm the seeded value is preserved (not zeroed).
        self.state.actors["USA"].territory.contested_zones["taiwan_strait"] = 0.72
        # No units anywhere.
        self.state.derive_contested_zones()
        self.assertAlmostEqual(
            self.state.actors["USA"].territory.contested_zones["taiwan_strait"], 0.72, places=3
        )


class DeriveContestedZonesFullScenarioTests(unittest.TestCase):
    def test_real_scenario_derivation_runs(self):
        """Smoke test: the full Taiwan scenario init triggers derivation via
        ensure_derived_state(); verify it doesn't crash and produces sensible
        per-zone control values."""
        state = TaiwanStraitScenario(seed=0, year_horizon="2026").initialize()
        state.ensure_derived_state()
        # Each zone with units should have control fractions that sum to 1.0
        # across the actors that have presence.
        for zone_id in ZONE_BBOXES:
            shares = [
                state.actors[actor].territory.contested_zones.get(zone_id, 0.0)
                for actor in state.actors
            ]
            # Shares can be 0 (no presence) or sum to ~1.0 (derived). Both OK.
            total = sum(shares)
            self.assertTrue(
                total < 0.01 or abs(total - 1.0) < 0.01,
                f"zone {zone_id} shares should sum to 0 or 1.0, got {total} (shares={shares})",
            )


if __name__ == "__main__":
    unittest.main()
