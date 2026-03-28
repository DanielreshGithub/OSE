import sys
import unittest

sys.dont_write_bytecode = True

from engine.event_generation import EventEligibilityEvaluator, EventTemplate
from scenarios.taiwan_strait import TaiwanStraitScenario


EXPECTED_SPECIFIC_EVENTS = {
    "kinmen_boarding_incident",
    "adiz_intrusion_wave",
    "undersea_cable_cut_matsu",
    "prc_tanker_seizure",
    "semiconductor_controls_expansion",
    "us_japan_air_defense_drill",
    "shipping_insurance_spike",
    "emergency_shipping_corridor_talks",
}


class EventGenerationTests(unittest.TestCase):
    def test_taiwan_strait_template_contains_new_specific_events(self):
        scenario = TaiwanStraitScenario(seed=0)
        event_ids = {template.event_id for template in scenario.build_event_templates()}
        self.assertTrue(EXPECTED_SPECIFIC_EVENTS.issubset(event_ids))

    def test_one_shot_event_is_rejected_after_occurrence(self):
        scenario = TaiwanStraitScenario(seed=0)
        state = scenario.initialize()
        capabilities = scenario.build_capability_profiles(state)
        recent_context = {
            "actions": {},
            "events": {},
            "descriptions": [],
            "event_occurrences": {"earthquake_taiwan": 1},
            "event_last_turns": {"earthquake_taiwan": 1},
        }
        pressures = scenario.derive_pressures(state, turn=2, recent_context=recent_context)
        evaluator = EventEligibilityEvaluator()

        candidates, audit = evaluator.evaluate(
            turn=2,
            state=state,
            pressures=pressures,
            capabilities=capabilities,
            event_templates=[
                EventTemplate(
                    event_id="earthquake_taiwan",
                    family="neutral_disturbance",
                    category="natural",
                    description="earthquake",
                    one_shot=True,
                )
            ],
            family_weights=scenario.build_family_weights(),
            recent_context=recent_context,
            scenario_context={},
        )

        self.assertEqual(candidates, [])
        self.assertTrue(audit["rejected_candidates"])
        self.assertIn("one_shot_already_triggered", audit["rejected_candidates"][0]["reasons"][0])

    def test_cooldown_event_is_rejected_while_recent(self):
        scenario = TaiwanStraitScenario(seed=0)
        state = scenario.initialize()
        capabilities = scenario.build_capability_profiles(state)
        recent_context = {
            "actions": {},
            "events": {},
            "descriptions": [],
            "event_occurrences": {"shipping_insurance_spike": 1},
            "event_last_turns": {"shipping_insurance_spike": 1},
        }
        pressures = scenario.derive_pressures(state, turn=3, recent_context=recent_context)
        evaluator = EventEligibilityEvaluator()

        candidates, audit = evaluator.evaluate(
            turn=3,
            state=state,
            pressures=pressures,
            capabilities=capabilities,
            event_templates=[
                EventTemplate(
                    event_id="shipping_insurance_spike",
                    family="economic_disruption",
                    category="economic",
                    description="shipping",
                    cooldown_turns=3,
                )
            ],
            family_weights=scenario.build_family_weights(),
            recent_context=recent_context,
            scenario_context={},
        )

        self.assertEqual(candidates, [])
        self.assertTrue(audit["rejected_candidates"])
        self.assertIn("cooldown_active", audit["rejected_candidates"][0]["reasons"][0])


if __name__ == "__main__":
    unittest.main()
