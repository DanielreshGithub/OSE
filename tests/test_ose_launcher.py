import sys
import unittest

sys.dont_write_bytecode = True

from cli.ose import normalize_invocation


class OSELauncherTests(unittest.TestCase):
    def test_operator_keyword_shorthand_normalizes_to_run_flags(self):
        command, argv = normalize_invocation(
            ["operator", "liberal", "model", "openai/gpt-4o", "turns", "3"]
        )
        self.assertEqual(command, "run")
        self.assertEqual(
            argv,
            ["--doctrine", "liberal", "--provider", "openrouter", "--model", "openai/gpt-4o", "--turns", "3"],
        )

    def test_bare_doctrine_and_model_shorthand_defaults_provider(self):
        command, argv = normalize_invocation(["constructivist", "openai/gpt-4o", "--turns", "5"])
        self.assertEqual(command, "run")
        self.assertEqual(
            argv,
            ["--doctrine", "constructivist", "--provider", "openrouter", "--model", "openai/gpt-4o", "--turns", "5"],
        )

    def test_reports_alias_routes_to_analysis(self):
        command, argv = normalize_invocation(["reports", "--output", "reports"])
        self.assertEqual(command, "report")
        self.assertEqual(argv, ["--output", "reports"])


if __name__ == "__main__":
    unittest.main()
