import os
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True

from cli import run as cli_run
from experiments import runner as experiment_runner


class CLIDefaultEnvTests(unittest.TestCase):
    def test_run_parser_uses_env_overrides(self):
        with patch.dict(
            os.environ,
            {
                "OSE_DEFAULT_TURNS": "7",
                "OSE_LOG_DIR": "tmp/runs",
                "OSE_SCENARIO_SEED": "11",
            },
            clear=False,
        ):
            parser = cli_run.build_parser()
            args = parser.parse_args([])

        self.assertEqual(args.turns, 7)
        self.assertEqual(args.log_dir, "tmp/runs")
        self.assertEqual(args.seed, 11)

    def test_experiment_parser_uses_env_overrides(self):
        with patch.dict(
            os.environ,
            {
                "OSE_DEFAULT_TURNS": "9",
                "OSE_SCENARIO_SEED": "13",
            },
            clear=False,
        ):
            parser = experiment_runner.build_parser()
            args = parser.parse_args([])

        self.assertEqual(args.turns, 9)
        self.assertEqual(args.seed, 13)


if __name__ == "__main__":
    unittest.main()
