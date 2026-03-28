import sys
import unittest

sys.dont_write_bytecode = True

from actors.persona import DOCTRINE_INSTRUCTIONS
from cli.run import VALID_DOCTRINES as CLI_DOCTRINES
from experiments.runner import VALID_DOCTRINES as RUNNER_DOCTRINES
from scoring.fidelity import DOCTRINE_RUBRICS


EXPECTED_DOCTRINES = {
    "realist",
    "liberal",
    "org_process",
    "constructivist",
    "marxist",
    "baseline",
}


class DoctrineProfileTests(unittest.TestCase):
    def test_doctrine_sets_match_across_system(self):
        self.assertEqual(set(CLI_DOCTRINES), EXPECTED_DOCTRINES)
        self.assertEqual(set(RUNNER_DOCTRINES), EXPECTED_DOCTRINES)
        self.assertEqual(set(DOCTRINE_INSTRUCTIONS.keys()), EXPECTED_DOCTRINES)
        self.assertEqual(set(DOCTRINE_RUBRICS.keys()), EXPECTED_DOCTRINES)


if __name__ == "__main__":
    unittest.main()
