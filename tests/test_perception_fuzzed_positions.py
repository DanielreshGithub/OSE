"""Tests for fuzzed unit positions in perception packets.

  - Own units appear with exact position.
  - Allied units appear with low noise.
  - Adversary surface units appear with larger noise.
  - Adversary submarines may go undetected at high uncertainty.
  - Same seed → same fuzzed coordinates (determinism preserved).
"""
from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from engine.perception import build_perception_packet
from scenarios.taiwan_strait import TaiwanStraitScenario


class FuzzedPositionTests(unittest.TestCase):
    def setUp(self):
        self.scenario = TaiwanStraitScenario(seed=42, year_horizon="2026")
        self.state = self.scenario.initialize()
        self.state.ensure_derived_state()

    def test_unit_positions_present_in_packet(self):
        usa = self.state.actors["USA"]
        packet, _ = build_perception_packet(usa, self.state)
        self.assertIn("unit_positions", packet)
        self.assertIsInstance(packet["unit_positions"], dict)
        self.assertGreater(len(packet["unit_positions"]), 0)

    def test_own_units_appear_with_exact_position(self):
        usa = self.state.actors["USA"]
        packet, meta = build_perception_packet(usa, self.state)
        for unit_id, unit in self.state.units.items():
            if unit.owner == "USA" and packet["unit_positions"][unit_id].get("detected"):
                perceived = packet["unit_positions"][unit_id]
                self.assertAlmostEqual(perceived["lat"], unit.lat, places=2)
                self.assertAlmostEqual(perceived["lon"], unit.lon, places=2)
                self.assertEqual(meta["unit_positions"][unit_id]["noise_deg"], 0.0)
                return
        self.fail("no US-owned detected unit found in USA's perception")

    def test_adversary_units_have_nonzero_noise(self):
        usa = self.state.actors["USA"]
        _, meta = build_perception_packet(usa, self.state)
        for unit_id, unit in self.state.units.items():
            if unit.owner == "PRC":
                noise = meta["unit_positions"][unit_id]["noise_deg"]
                self.assertGreater(noise, 0.0)
                return
        self.fail("no PRC unit found")

    def test_allied_units_have_lower_noise_than_adversary(self):
        usa = self.state.actors["USA"]
        _, meta = build_perception_packet(usa, self.state)
        jpn_noises = [
            meta["unit_positions"][uid]["noise_deg"]
            for uid, u in self.state.units.items() if u.owner == "JPN"
        ]
        prc_noises = [
            meta["unit_positions"][uid]["noise_deg"]
            for uid, u in self.state.units.items() if u.owner == "PRC"
        ]
        self.assertTrue(jpn_noises)
        self.assertTrue(prc_noises)
        self.assertLess(
            max(jpn_noises), max(prc_noises),
            "adversary noise should exceed ally noise",
        )

    def test_submarine_noise_higher_than_surface(self):
        # PRC submarines should carry larger noise than PRC surface units.
        usa = self.state.actors["USA"]
        _, meta = build_perception_packet(usa, self.state)
        sub_noises = [
            meta["unit_positions"][uid]["noise_deg"]
            for uid, u in self.state.units.items()
            if u.owner == "PRC" and u.unit_type in ("submarine", "ssbn")
        ]
        surface_noises = [
            meta["unit_positions"][uid]["noise_deg"]
            for uid, u in self.state.units.items()
            if u.owner == "PRC" and u.unit_type in ("destroyer", "frigate", "csg", "surface_action_group")
        ]
        self.assertTrue(sub_noises)
        self.assertTrue(surface_noises)
        # The maximum submarine noise should meet or exceed the max surface noise.
        self.assertGreaterEqual(max(sub_noises), max(surface_noises))

    def test_same_seed_same_fuzzed_positions(self):
        usa = self.state.actors["USA"]
        packet1, _ = build_perception_packet(usa, self.state)
        packet2, _ = build_perception_packet(usa, self.state)
        for unit_id, unit in self.state.units.items():
            if unit.owner == "PRC" and packet1["unit_positions"][unit_id].get("detected"):
                self.assertEqual(
                    packet1["unit_positions"][unit_id]["lat"],
                    packet2["unit_positions"][unit_id]["lat"],
                )
                self.assertEqual(
                    packet1["unit_positions"][unit_id]["lon"],
                    packet2["unit_positions"][unit_id]["lon"],
                )
                return


if __name__ == "__main__":
    unittest.main()
