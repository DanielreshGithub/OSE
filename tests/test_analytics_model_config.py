import importlib
import os
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True


class AnalyticsModelConfigTests(unittest.TestCase):
    def test_shared_analytics_model_env_is_used_by_both_modules(self):
        with patch.dict(os.environ, {"OSE_ANALYTICS_MODEL": "claude-opus-test"}, clear=False):
            import scoring.fidelity as fidelity
            import analysis.analyst as analyst

            importlib.reload(fidelity)
            importlib.reload(analyst)

            self.assertEqual(fidelity.SCORER_MODEL, "claude-opus-test")
            self.assertEqual(analyst.ANALYST_MODEL, "claude-opus-test")

        importlib.reload(fidelity)
        importlib.reload(analyst)

    def test_specific_env_vars_override_shared_analytics_model(self):
        with patch.dict(
            os.environ,
            {
                "OSE_ANALYTICS_MODEL": "shared-opus",
                "OSE_SCORER_MODEL": "scorer-opus",
                "OSE_ANALYST_MODEL": "analyst-opus",
            },
            clear=False,
        ):
            import scoring.fidelity as fidelity
            import analysis.analyst as analyst

            importlib.reload(fidelity)
            importlib.reload(analyst)

            self.assertEqual(fidelity.SCORER_MODEL, "scorer-opus")
            self.assertEqual(analyst.ANALYST_MODEL, "analyst-opus")

        importlib.reload(fidelity)
        importlib.reload(analyst)


if __name__ == "__main__":
    unittest.main()
