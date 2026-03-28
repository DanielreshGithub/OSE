import sys
import unittest

sys.dont_write_bytecode = True

from engine.actions import ACTION_REGISTRY, parse_action_from_dict
from scoring.bci import ACTION_CATEGORIES


EXPECTED_NEW_ACTIONS = {
    "deploy_forward",
    "lawfare_filing",
    "multilateral_appeal",
    "expel_diplomats",
    "asset_freeze",
    "supply_chain_diversion",
    "hack_and_leak",
}


class ActionRegistryTests(unittest.TestCase):
    def test_registry_count_and_new_actions(self):
        self.assertEqual(len(ACTION_REGISTRY), 32)
        self.assertTrue(EXPECTED_NEW_ACTIONS.issubset(set(ACTION_REGISTRY.keys())))

    def test_bci_categories_cover_registry(self):
        self.assertEqual(set(ACTION_REGISTRY.keys()), set(ACTION_CATEGORIES.keys()))

    def test_new_actions_parse_from_dict(self):
        for action_name in EXPECTED_NEW_ACTIONS:
            action = parse_action_from_dict({
                "action_type": action_name,
                "actor_id": "USA",
                "rationale": "registry test",
            })
            self.assertEqual(action.action_type, action_name)


if __name__ == "__main__":
    unittest.main()
