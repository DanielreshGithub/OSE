"""Tests for the operational military doctrine narrative layer.

Verifies that:
  - All four Taiwan Strait actors have non-empty doctrine narratives loaded
    from scenarios/data/doctrine_*.md.
  - The narrative appears in the LLM system prompt in 'full' mode.
  - The narrative is trimmed (not omitted) in 'compact' mode.
  - The minimal-mode fallback string is used in 'minimal' mode.
"""
from __future__ import annotations

import sys
import unittest

sys.dont_write_bytecode = True

from actors.persona import build_persona_prompt
from scenarios.taiwan_strait import TaiwanStraitScenario, _load_doctrine


class DoctrineNarrativeTests(unittest.TestCase):
    def setUp(self):
        self.state = TaiwanStraitScenario(seed=0).initialize()

    def test_all_actors_have_non_empty_doctrine(self):
        for short_name, actor in self.state.actors.items():
            with self.subTest(actor=short_name):
                self.assertTrue(
                    actor.military_doctrine_narrative,
                    f"{short_name} doctrine narrative is empty",
                )
                self.assertGreater(
                    len(actor.military_doctrine_narrative),
                    500,
                    f"{short_name} doctrine narrative is suspiciously short",
                )

    def test_doctrine_loader_returns_empty_for_missing(self):
        self.assertEqual(_load_doctrine("XXX_does_not_exist"), "")

    def test_doctrine_appears_in_full_prompt(self):
        actor = self.state.actors["USA"]
        prompt = build_persona_prompt(actor, "baseline", prompt_mode="full")
        self.assertIn("How You Fight (Revealed Military Doctrine)", prompt)
        # Substring unique to the USA doctrine file:
        self.assertIn("air-superiority-first", prompt)

    def test_doctrine_distinct_per_actor(self):
        prc_prompt = build_persona_prompt(self.state.actors["PRC"], "baseline", prompt_mode="full")
        twn_prompt = build_persona_prompt(self.state.actors["TWN"], "baseline", prompt_mode="full")
        jpn_prompt = build_persona_prompt(self.state.actors["JPN"], "baseline", prompt_mode="full")
        # Each actor's doctrine includes a unique signature phrase.
        self.assertIn("salami slicing", prc_prompt.lower())
        self.assertIn("porcupine strategy", twn_prompt.lower())
        self.assertIn("senshu boei", jpn_prompt.lower())

    def test_compact_mode_trims_doctrine(self):
        actor = self.state.actors["USA"]
        compact = build_persona_prompt(actor, "baseline", prompt_mode="compact")
        full = build_persona_prompt(actor, "baseline", prompt_mode="full")
        # Doctrine section is present in both but compact is shorter.
        self.assertIn("How You Fight (Revealed Military Doctrine)", compact)
        self.assertLess(len(compact), len(full))

    def test_minimal_mode_uses_fallback(self):
        actor = self.state.actors["USA"]
        prompt = build_persona_prompt(actor, "baseline", prompt_mode="minimal")
        self.assertIn("Fight in a manner consistent", prompt)
        # The full USA-specific signature phrase should NOT leak into minimal mode.
        self.assertNotIn("air-superiority-first", prompt)


if __name__ == "__main__":
    unittest.main()
