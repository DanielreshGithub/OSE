"""Tests for HumanDecisionActor.

Uses injected `input_fn`/`print_fn` rather than patching builtins, so each
test scripts its own prompt sequence against a fresh actor.
"""
from __future__ import annotations

import sys
import unittest
from typing import List

sys.dont_write_bytecode = True

from actors.human_actor import HumanDecisionActor
from engine.actions import get_available_actions_for
from scenarios.taiwan_strait import TaiwanStraitScenario


def make_state():
    scenario = TaiwanStraitScenario(seed=0)
    state = scenario.initialize()
    state.ensure_derived_state()
    return state


def scripted_input(answers: List[str]):
    """Returns an input_fn that yields scripted answers in order."""
    queue = list(answers)
    def _fn(_prompt: str) -> str:
        if not queue:
            raise AssertionError(f"HumanDecisionActor asked too many questions; ran out of scripted answers. Prompt was: {_prompt!r}")
        return queue.pop(0)
    return _fn


def silent_print(_msg: str) -> None:
    return None


class HumanDecisionActorTests(unittest.TestCase):
    def setUp(self):
        self.state = make_state()
        self.actor_obj = self.state.actors["USA"]

    def test_decide_returns_action_and_record(self):
        # Pick hold_position by name; skip target prompt (auto-skipped); default intensity; empty rationale.
        actor = HumanDecisionActor(
            actor=self.actor_obj,
            run_id="test-run",
            input_fn=scripted_input(["hold_position", "", ""]),
            print_fn=silent_print,
        )
        action, record = actor.decide(self.state)
        self.assertEqual(action.action_type, "hold_position")
        self.assertEqual(action.actor_id, "USA")
        self.assertEqual(record.provider_name, "human")
        self.assertEqual(record.model_id, "human")
        self.assertEqual(record.validation_result, "valid")
        self.assertTrue(record.final_applied)
        self.assertEqual(record.reasoning_trace, "[no rationale]")
        self.assertEqual(record.actor_short_name, "USA")
        self.assertEqual(record.parsed_action["action_type"], "hold_position")

    def test_rationale_captured(self):
        actor = HumanDecisionActor(
            actor=self.actor_obj,
            run_id="test-run",
            input_fn=scripted_input(["monitor", "", "watching PRC fleet"]),
            print_fn=silent_print,
        )
        _, record = actor.decide(self.state)
        self.assertEqual(record.reasoning_trace, "watching PRC fleet")

    def test_numbered_menu_pick_succeeds(self):
        # Pick by index against a known no-target action (monitor).
        available = sorted(get_available_actions_for("USA", self.state))
        self.assertIn("monitor", available)
        monitor_index = str(available.index("monitor") + 1)
        actor = HumanDecisionActor(
            actor=self.actor_obj,
            run_id="test-run",
            input_fn=scripted_input([monitor_index, "", ""]),
            print_fn=silent_print,
        )
        action, record = actor.decide(self.state)
        self.assertEqual(action.actor_id, "USA")
        self.assertEqual(action.action_type, "monitor")
        self.assertEqual(record.parsed_action["action_type"], "monitor")

    def test_invalid_then_valid_action_reprompts(self):
        # First answer is an unknown action name -> reprompt -> then valid hold_position.
        actor = HumanDecisionActor(
            actor=self.actor_obj,
            run_id="test-run",
            input_fn=scripted_input(["not_a_real_action", "hold_position", "", ""]),
            print_fn=silent_print,
        )
        action, record = actor.decide(self.state)
        self.assertEqual(action.action_type, "hold_position")
        self.assertEqual(record.validation_result, "valid")

    def test_target_prompt_skipped_for_hold(self):
        # hold_position should NOT consume a target answer. If it did, the
        # scripted queue would run out before we got to rationale.
        actor = HumanDecisionActor(
            actor=self.actor_obj,
            run_id="test-run",
            input_fn=scripted_input(["hold_position", "low", "stand-down"]),
            print_fn=silent_print,
        )
        action, record = actor.decide(self.state)
        self.assertEqual(action.action_type, "hold_position")
        self.assertEqual(action.intensity, "low")
        self.assertEqual(record.reasoning_trace, "stand-down")

    def test_target_actor_by_index(self):
        # negotiate is normally always available; pick PRC by index.
        actor = HumanDecisionActor(
            actor=self.actor_obj,
            run_id="test-run",
            input_fn=scripted_input(["negotiate", "1", "", "open back-channel"]),
            print_fn=silent_print,
        )
        action, _ = actor.decide(self.state)
        self.assertEqual(action.action_type, "negotiate")
        # The first "other actor" in iteration order depends on dict insertion;
        # accept any non-self actor as the target.
        self.assertIn(action.target_actor, {n for n in self.state.actors if n != "USA"})


if __name__ == "__main__":
    unittest.main()
