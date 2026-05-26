"""Tests for the haversine-based MovementResolver.

Reference distances are sanity-checked against publicly-known approximate
great-circle distances rounded to nearest 10 km (haversine over a spherical
Earth diverges from WGS84 by < 0.5%).
"""
from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from world.state import Unit
from engine.movement import (
    compute_distance_km,
    move_unit_toward,
    units_within_radius,
    unit_can_reach,
    ARRIVAL_THRESHOLD_KM,
)


def _make_unit(unit_id="U", lat=0.0, lon=0.0, range_km=1000.0, state="standby"):
    return Unit(
        unit_id=unit_id,
        owner="USA",
        unit_type="destroyer",
        platform_class="X",
        lat=lat, lon=lon,
        speed_kts=25,
        range_km_per_turn=range_km,
        state=state,
    )


class HaversineTests(unittest.TestCase):
    def test_zero_distance(self):
        self.assertAlmostEqual(compute_distance_km(35.0, 139.0, 35.0, 139.0), 0.0, places=2)

    def test_yokosuka_to_bashi_channel(self):
        # Yokosuka 35.29N 139.66E to Bashi Channel 21.5N 121.0E
        # Reference open-source value: ~2400 km
        d = compute_distance_km(35.29, 139.66, 21.5, 121.0)
        self.assertGreater(d, 2300)
        self.assertLess(d, 2500)

    def test_taipei_to_beijing(self):
        # Taipei 25.04N 121.56E to Beijing 39.90N 116.41E
        # Reference: ~1730 km
        d = compute_distance_km(25.04, 121.56, 39.90, 116.41)
        self.assertGreater(d, 1650)
        self.assertLess(d, 1800)

    def test_distance_symmetric(self):
        d1 = compute_distance_km(35.29, 139.66, 21.5, 121.0)
        d2 = compute_distance_km(21.5, 121.0, 35.29, 139.66)
        self.assertAlmostEqual(d1, d2, places=2)


class MovementTests(unittest.TestCase):
    def test_unit_arrives_when_within_range(self):
        # CSG at Yokosuka (35.29, 139.66) with 1300 km/turn range moving to
        # nearby point ~500 km away should arrive in one turn.
        unit = _make_unit(lat=35.29, lon=139.66, range_km=1300)
        move_unit_toward(unit, 31.0, 135.0)  # ~600 km southwest
        self.assertEqual(unit.state, "on_station")
        self.assertAlmostEqual(unit.lat, 31.0, places=4)
        self.assertAlmostEqual(unit.lon, 135.0, places=4)

    def test_unit_partial_transit(self):
        # 2400 km journey with 1300 km/turn range → unit moves partially, enters transit.
        unit = _make_unit(lat=35.29, lon=139.66, range_km=1300)
        move_unit_toward(unit, 21.5, 121.0)
        self.assertEqual(unit.state, "transit")
        # Destination should be recorded for next turn
        self.assertEqual(unit.destination_lat, 21.5)
        self.assertEqual(unit.destination_lon, 121.0)
        # New position should be between origin and destination
        d_remaining = compute_distance_km(unit.lat, unit.lon, 21.5, 121.0)
        self.assertGreater(d_remaining, 0)
        self.assertLess(d_remaining, 2400)

    def test_multi_turn_transit_reaches_destination(self):
        unit = _make_unit(lat=35.29, lon=139.66, range_km=1300)
        # Should arrive within 2 turns (2400 km / 1300 km/turn = 1.85 turns)
        for _ in range(3):
            move_unit_toward(unit, 21.5, 121.0)
            if unit.state == "on_station":
                break
        self.assertEqual(unit.state, "on_station")

    def test_immobile_unit_stays_put(self):
        unit = _make_unit(lat=35.29, lon=139.66, range_km=0)
        move_unit_toward(unit, 21.5, 121.0)
        # Position unchanged
        self.assertAlmostEqual(unit.lat, 35.29, places=4)
        self.assertAlmostEqual(unit.lon, 139.66, places=4)
        # Destination still recorded for visibility
        self.assertEqual(unit.destination_lat, 21.5)

    def test_arrival_threshold_snaps_to_destination(self):
        # Place unit 10 km from destination, well within arrival threshold.
        unit = _make_unit(lat=35.29, lon=139.66, range_km=1300)
        # 0.05° lat ≈ 5.5 km — within ARRIVAL_THRESHOLD_KM
        move_unit_toward(unit, 35.34, 139.66)
        self.assertEqual(unit.state, "on_station")


class UnitsWithinRadiusTests(unittest.TestCase):
    def test_filters_units_correctly(self):
        units = [
            _make_unit("A", 35.29, 139.66),  # Yokosuka
            _make_unit("B", 33.16, 129.72),  # Sasebo, ~1000 km from Yokosuka
            _make_unit("C", 35.30, 139.67),  # Adjacent to A
        ]
        within_500 = units_within_radius(units, 35.29, 139.66, 500)
        ids = {u.unit_id for u in within_500}
        self.assertIn("A", ids)
        self.assertIn("C", ids)
        self.assertNotIn("B", ids)


class UnitCanReachTests(unittest.TestCase):
    def test_in_range_returns_true(self):
        unit = _make_unit(lat=35.29, lon=139.66, range_km=1300)
        self.assertTrue(unit_can_reach(unit, 31.0, 135.0, turns=1))

    def test_out_of_range_single_turn_returns_false(self):
        unit = _make_unit(lat=35.29, lon=139.66, range_km=1300)
        self.assertFalse(unit_can_reach(unit, 21.5, 121.0, turns=1))

    def test_out_of_range_reachable_in_multiple_turns(self):
        unit = _make_unit(lat=35.29, lon=139.66, range_km=1300)
        self.assertTrue(unit_can_reach(unit, 21.5, 121.0, turns=2))

    def test_immobile_unit_at_destination_returns_true(self):
        unit = _make_unit(lat=35.29, lon=139.66, range_km=0)
        # Within arrival threshold counts as "can reach"
        self.assertTrue(unit_can_reach(unit, 35.29, 139.66, turns=1))

    def test_immobile_unit_far_from_destination_returns_false(self):
        unit = _make_unit(lat=35.29, lon=139.66, range_km=0)
        self.assertFalse(unit_can_reach(unit, 21.5, 121.0, turns=1))


if __name__ == "__main__":
    unittest.main()
