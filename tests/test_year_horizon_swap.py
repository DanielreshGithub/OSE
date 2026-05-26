"""Tests for the year_horizon parameter in TaiwanStraitScenario.

Asserts that:
  - 2026 baseline yields the recalibrated current-force capability values.
  - 2030 projected yields the higher projected capability values.
  - Invalid year_horizon raises a clear error.
  - The 2030 unit roster is a strict superset of the 2026 roster.
"""
from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from scenarios.taiwan_strait import TaiwanStraitScenario


class YearHorizonSwapTests(unittest.TestCase):
    def test_2026_baseline_capability_values(self):
        state = TaiwanStraitScenario(seed=0, year_horizon="2026").initialize()
        self.assertAlmostEqual(state.actors["PRC"].military.amphibious_capacity, 0.62, places=3)
        self.assertAlmostEqual(state.actors["PRC"].military.nuclear_capability, 0.58, places=3)
        self.assertAlmostEqual(state.actors["TWN"].military.a2ad_effectiveness, 0.55, places=3)

    def test_2030_projected_capability_values(self):
        state = TaiwanStraitScenario(seed=0, year_horizon="2030").initialize()
        self.assertAlmostEqual(state.actors["PRC"].military.amphibious_capacity, 0.72, places=3)
        self.assertAlmostEqual(state.actors["PRC"].military.nuclear_capability, 0.72, places=3)
        self.assertAlmostEqual(state.actors["TWN"].military.a2ad_effectiveness, 0.72, places=3)

    def test_invalid_year_horizon_rejected(self):
        with self.assertRaises(ValueError):
            TaiwanStraitScenario(seed=0, year_horizon="2099")

    def test_default_horizon_is_2026(self):
        scenario = TaiwanStraitScenario(seed=0)
        self.assertEqual(scenario.year_horizon, "2026")

    def test_2030_adds_units_not_in_2026(self):
        state_2026 = TaiwanStraitScenario(seed=0, year_horizon="2026").initialize()
        state_2030 = TaiwanStraitScenario(seed=0, year_horizon="2030").initialize()
        # 2030 strict superset of 2026 (2026 IDs all present in 2030, plus new ones)
        self.assertGreater(len(state_2030.units), len(state_2026.units))
        for unit_id in state_2026.units:
            self.assertIn(unit_id, state_2030.units, f"{unit_id} missing in 2030 roster")
        # Confirm at least one signature 2030-only platform
        self.assertIn("PRC_CV_FUJIAN", state_2030.units)
        self.assertNotIn("PRC_CV_FUJIAN", state_2026.units)

    def test_scenario_id_reflects_year(self):
        state_2026 = TaiwanStraitScenario(seed=0, year_horizon="2026").initialize()
        state_2030 = TaiwanStraitScenario(seed=0, year_horizon="2030").initialize()
        self.assertEqual(state_2026.scenario_id, "taiwan_strait_2026")
        self.assertEqual(state_2030.scenario_id, "taiwan_strait_2030")


if __name__ == "__main__":
    unittest.main()
