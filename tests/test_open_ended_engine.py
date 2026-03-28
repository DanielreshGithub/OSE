import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

from actors.base import ActorInterface
from engine.actions import MonitorAction
from engine.loop import SimulationEngine
from scenarios.taiwan_strait import TaiwanStraitScenario
from world.events import DecisionRecord


class ScriptedActor(ActorInterface):
    def __init__(self, short_name: str):
        self.short_name = short_name

    def decide(self, state):
        action = MonitorAction(
            action_type="monitor",
            actor_id=self.short_name,
            rationale="Deterministic monitor action for test coverage.",
        )
        record = DecisionRecord(
            turn=state.turn,
            actor_short_name=self.short_name,
            doctrine_condition="baseline",
            run_id="test",
            system_prompt="test",
            perception_block="{}",
            perception_metadata={},
            reasoning_trace="monitor",
            raw_llm_response="monitor",
            parsed_action={"action_type": "monitor"},
            validation_result="valid",
            final_applied=True,
            crisis_phase_at_decision=state.crisis_phase,
        )
        return action, record


def _run_summary(seed: int):
    scenario = TaiwanStraitScenario(seed=seed)
    state = scenario.initialize()
    actors = {name: ScriptedActor(name) for name in state.actors}
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = SimulationEngine(
            state=state,
            actors=actors,
            doctrine_condition="baseline",
            run_id=f"test_{seed}",
            run_number=1,
            seed=seed,
            log_dir=tmpdir,
            verbose=False,
            scenario=scenario,
        )
        final_state, outcome = engine.run(max_turns=3)
        return {
            "outcome": outcome,
            "tension": round(final_state.global_tension, 4),
            "phase": final_state.crisis_phase,
            "turn_logs": [
                {
                    "turn": log.turn,
                    "pressure_before": log.pressure_before,
                    "pressure_after": log.pressure_after,
                    "event_generation_audit": log.event_generation_audit,
                    "terminal_checks": log.terminal_checks,
                    "events": [e.description for e in log.events_this_turn],
                    "cascades": [e.description for e in log.cascade_events],
                }
                for log in final_state.turn_logs
            ],
        }


class OpenEndedEngineTests(unittest.TestCase):
    def test_same_seed_replays_identically(self):
        first = _run_summary(17)
        second = _run_summary(17)
        self.assertEqual(first, second)

    def test_state_derives_capabilities_and_pressures(self):
        scenario = TaiwanStraitScenario(seed=5)
        state = scenario.initialize()
        state.ensure_derived_state()

        for actor in state.actors.values():
            self.assertIsNotNone(actor.capabilities)

        events = scenario.get_turn_events(0, state)
        audit_events = [
            event for event in events
            if "pressure_snapshot" in (event.world_state_delta or {})
        ]
        self.assertTrue(audit_events)

    def test_turn_logs_capture_open_ended_audit_fields(self):
        summary = _run_summary(23)
        self.assertTrue(summary["turn_logs"])
        first_turn = summary["turn_logs"][0]
        self.assertIn("values", first_turn["pressure_before"])
        self.assertIn("values", first_turn["pressure_after"])
        self.assertTrue(first_turn["event_generation_audit"])
        self.assertIn("war_failure", first_turn["terminal_checks"])


if __name__ == "__main__":
    unittest.main()
