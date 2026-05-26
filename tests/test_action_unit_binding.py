"""Tests for the Phase B action↔unit binding.

When an action carries unit_ids + a destination, the resolver should move
those units; without unit_ids, the legacy scalar resolution path runs.
"""
from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from world.events import DecisionRecord
from engine.actions import DeployForwardAction, AdvanceAction, parse_action_from_dict
from engine.resolver import TurnResolver
from scenarios.taiwan_strait import TaiwanStraitScenario


def _record_for(action):
    return DecisionRecord(
        turn=0, actor_short_name=action.actor_id, doctrine_condition="baseline",
        run_id="test", system_prompt="", perception_block="",
        reasoning_trace="", raw_llm_response="", validation_result="valid",
        final_applied=True,
    )


class ActionUnitBindingTests(unittest.TestCase):
    def setUp(self):
        self.scenario = TaiwanStraitScenario(seed=0, year_horizon="2026")
        self.state = self.scenario.initialize()
        self.state.ensure_derived_state()
        self.resolver = TurnResolver()

    def test_deploy_forward_with_unit_ids_moves_unit(self):
        # Take a US CSG and order it toward bashi_channel
        unit_id = "USA_CSG_RR"
        prev_lat = self.state.units[unit_id].lat
        prev_lon = self.state.units[unit_id].lon
        prev_state = self.state.units[unit_id].state

        action = DeployForwardAction(
            actor_id="USA",
            rationale="test",
            unit_ids=[unit_id],
            target_location_ref="bashi_channel",
        )
        valid, errors = action.is_valid(self.state)
        self.assertTrue(valid, f"action should validate; errors={errors}")

        decisions = {"USA": (action, _record_for(action))}
        new_state, events = self.resolver.resolve(decisions, self.state)

        moved = new_state.units[unit_id]
        # Position must have changed (Yokosuka → toward Bashi is a big leg)
        self.assertTrue(
            (moved.lat, moved.lon) != (prev_lat, prev_lon),
            f"unit {unit_id} did not move (was {prev_lat},{prev_lon} still {moved.lat},{moved.lon})",
        )
        # State should reflect transit or on_station
        self.assertIn(moved.state, ("transit", "on_station"))
        # At least one movement event should be emitted
        movement_events = [e for e in events if unit_id in e.description]
        self.assertGreater(len(movement_events), 0)

    def test_deploy_forward_without_unit_ids_falls_back_to_scalar(self):
        # Pure legacy form — no unit_ids
        action = DeployForwardAction(
            actor_id="USA",
            rationale="test",
            target_zone="taiwan_strait",
        )
        valid, errors = action.is_valid(self.state)
        self.assertTrue(valid, f"legacy action should still validate; errors={errors}")

        # No movement event tied to a specific unit_id should fire
        decisions = {"USA": (action, _record_for(action))}
        _new_state, events = self.resolver.resolve(decisions, self.state)
        # Any USA-caused events should be fine; we just ensure no crash.
        self.assertIsInstance(events, list)

    def test_unit_ids_owned_by_wrong_actor_rejected(self):
        # PRC tries to move a USA unit
        action = DeployForwardAction(
            actor_id="PRC",
            rationale="test",
            unit_ids=["USA_CSG_RR"],
            target_location_ref="bashi_channel",
        )
        valid, errors = action.is_valid(self.state)
        self.assertFalse(valid)
        # Error should mention ownership
        self.assertTrue(
            any("not owned by" in e for e in errors),
            f"expected ownership error; got {errors}",
        )

    def test_unknown_unit_id_rejected(self):
        action = DeployForwardAction(
            actor_id="USA",
            rationale="test",
            unit_ids=["USA_NONEXISTENT"],
            target_location_ref="bashi_channel",
        )
        valid, errors = action.is_valid(self.state)
        self.assertFalse(valid)
        self.assertTrue(any("Unknown unit_id" in e for e in errors))

    def test_unknown_location_ref_rejected(self):
        action = DeployForwardAction(
            actor_id="USA",
            rationale="test",
            unit_ids=["USA_CSG_RR"],
            target_location_ref="atlantis",
        )
        valid, errors = action.is_valid(self.state)
        self.assertFalse(valid)
        self.assertTrue(any("not in named_locations" in e for e in errors))

    def test_unit_ids_without_destination_rejected(self):
        action = DeployForwardAction(
            actor_id="USA",
            rationale="test",
            unit_ids=["USA_CSG_RR"],
            # No target_location or target_location_ref
        )
        valid, errors = action.is_valid(self.state)
        self.assertFalse(valid)
        self.assertTrue(any("cannot resolve destination" in e for e in errors))

    def test_immobile_unit_rejected_for_distant_destination(self):
        # An infantry brigade with range=0 can't deploy_forward to bashi_channel
        action = DeployForwardAction(
            actor_id="USA",
            rationale="test",
            unit_ids=["USA_BCT_OKINAWA"],  # range_km_per_turn=0
            target_location_ref="bashi_channel",
        )
        valid, errors = action.is_valid(self.state)
        self.assertFalse(valid)
        self.assertTrue(any("immobile" in e for e in errors))

    def test_action_dict_round_trips_with_unit_ids(self):
        # parse_action_from_dict must accept the new fields
        action = parse_action_from_dict({
            "action_type": "deploy_forward",
            "actor_id": "USA",
            "unit_ids": ["USA_CSG_RR"],
            "target_location_ref": "bashi_channel",
            "rationale": "x",
        })
        self.assertEqual(action.unit_ids, ["USA_CSG_RR"])
        self.assertEqual(action.target_location_ref, "bashi_channel")


if __name__ == "__main__":
    unittest.main()
