import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True

from analysis.__main__ import _normalize_args, main as analysis_main
from analysis.analyst import _build_inflections_block, _build_statistics_block
from analysis.engine import AnalysisEngine
from analysis.report import generate_report, main as report_main
from analysis.renderer import MarkdownRenderer
from logs.logger import StructuredLogger
from world.events import DecisionRecord, RunRecord, TurnLog


def _write_sample_run(
    log_dir: str,
    run_id: str,
    doctrine: str,
    provider_name: str,
    model_id: str,
    outcome: str,
    final_tension: float,
):
    logger = StructuredLogger(log_dir=log_dir, run_id=run_id)
    logger.start_run(
        RunRecord(
            run_id=run_id,
            scenario_name="Taiwan Strait Crisis 2026",
            doctrine_condition=doctrine,
            provider_name=provider_name,
            model_id=model_id,
            run_number=1,
            seed=0,
            total_turns=1,
            final_crisis_phase="tension",
            final_global_tension=final_tension,
        )
    )
    logger.log_decision(
        DecisionRecord(
            turn=0,
            actor_short_name="USA",
            doctrine_condition=doctrine,
            run_id=run_id,
            provider_name=provider_name,
            model_id=model_id,
            system_prompt="system",
            perception_block="{}",
            perception_metadata={},
            reasoning_trace="Use a back channel to reduce uncertainty and preserve flexibility.",
            raw_llm_response='{"tool": "submit_action"}',
            parsed_action={
                "action_type": "back_channel",
                "target_actor": "PRC",
                "intensity": "medium",
            },
            validation_result="valid",
            final_applied=True,
            crisis_phase_at_decision="tension",
        )
    )
    logger.log_turn(
        TurnLog(
            run_id=run_id,
            turn=0,
            doctrine_condition=doctrine,
            crisis_phase="tension",
            global_tension=final_tension,
            pressure_before={"values": {"military_pressure": 0.4}},
            pressure_after={"values": {"military_pressure": 0.35}},
            event_generation_audit=[],
            perception_packets={},
            state_mutations=[],
            terminal_checks={},
            world_state_snapshot={},
        )
    )
    logger.complete_run(
        run_id=run_id,
        total_turns=1,
        final_crisis_phase="tension",
        final_global_tension=final_tension,
        outcome_classification=outcome,
    )
    logger.close()
    return str(Path(log_dir) / f"{run_id}.db")


class AnalysisReportingTests(unittest.TestCase):
    def test_analysis_engine_tracks_provider_model_and_run_inventory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_paths = [
                _write_sample_run(
                    tmpdir,
                    "run_gpt4o",
                    "liberal",
                    "openrouter",
                    "openai/gpt-4o",
                    "deterrence_success",
                    0.24,
                ),
                _write_sample_run(
                    tmpdir,
                    "run_grok",
                    "liberal",
                    "openrouter",
                    "x-ai/grok-4.1-fast",
                    "frozen_conflict",
                    0.48,
                ),
            ]

            report_data = AnalysisEngine().analyze(db_paths)

        meta = report_data["metadata"]
        self.assertEqual(meta["providers"], ["openrouter"])
        self.assertEqual(
            meta["models"],
            ["openai/gpt-4o", "x-ai/grok-4.1-fast"],
        )
        self.assertTrue(meta["mixed_model_report"])
        self.assertEqual(len(report_data["run_inventory"]), 2)
        self.assertIn("liberal | openrouter | openai/gpt-4o", report_data["by_configuration"])
        self.assertIn("liberal | openrouter | x-ai/grok-4.1-fast", report_data["by_configuration"])
        self.assertTrue(report_data["inflection_decisions"])
        self.assertEqual(
            report_data["inflection_decisions"][0]["provider_name"],
            "openrouter",
        )

    def test_report_text_surfaces_model_identity(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_paths = [
                _write_sample_run(
                    tmpdir,
                    "run_gpt4o",
                    "liberal",
                    "openrouter",
                    "openai/gpt-4o",
                    "deterrence_success",
                    0.24,
                ),
                _write_sample_run(
                    tmpdir,
                    "run_grok",
                    "liberal",
                    "openrouter",
                    "x-ai/grok-4.1-fast",
                    "frozen_conflict",
                    0.48,
                ),
            ]
            report_data = AnalysisEngine().analyze(db_paths)

        stats_block = _build_statistics_block(report_data)
        inflections_block = _build_inflections_block(report_data["inflection_decisions"])
        markdown = MarkdownRenderer().render(report_data)

        self.assertIn("Providers tested", stats_block)
        self.assertIn("openai/gpt-4o", stats_block)
        self.assertIn("x-ai/grok-4.1-fast", stats_block)
        self.assertIn("Provider / Model", inflections_block)
        self.assertIn("## Configuration Summary", markdown)
        self.assertIn("## Run Inventory", markdown)
        self.assertIn("x-ai/grok-4.1-fast", markdown)

    def test_analysis_entrypoint_accepts_reports_alias(self):
        self.assertEqual(
            _normalize_args(["reports", "--runs", "logs/runs"]),
            ["--runs", "logs/runs"],
        )
        with patch("analysis.__main__.report_main") as report_main:
            analysis_main(["reports", "--runs", "logs/runs"])
        report_main.assert_called_once_with(["--runs", "logs/runs"])

    def test_report_cli_defaults_to_logs_runs(self):
        with patch("analysis.report.discover_databases", return_value=["logs/runs/example.db"]) as discover:
            with patch(
                "analysis.report.generate_report",
                return_value={"markdown": "reports/example.md"},
            ) as generate:
                report_main([])

        discover.assert_called_once_with("logs/runs")
        generate.assert_called_once_with(
            db_paths=["logs/runs/example.db"],
            use_llm=False,
            use_latex=False,
            output_dir="reports",
        )

    def test_generate_report_creates_graphs_and_skips_bci_for_single_runs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_paths = [
                _write_sample_run(
                    tmpdir,
                    "run_gpt4o",
                    "liberal",
                    "openrouter",
                    "openai/gpt-4o",
                    "deterrence_success",
                    0.24,
                ),
                _write_sample_run(
                    tmpdir,
                    "run_grok",
                    "liberal",
                    "openrouter",
                    "x-ai/grok-4.1-fast",
                    "frozen_conflict",
                    0.48,
                ),
            ]
            output_dir = Path(tmpdir) / "reports"
            result = generate_report(db_paths=db_paths, output_dir=str(output_dir))

            markdown = Path(result["markdown"]).read_text()
            json_payload = Path(result["json"]).read_text()
            asset_dir = Path(result["markdown"]).with_suffix("")
            asset_root = Path(str(asset_dir) + "_assets")

            self.assertTrue(asset_root.exists())
            self.assertTrue(any(asset_root.glob("*.svg")))

        self.assertIn("## Visual Summary", markdown)
        self.assertIn("## Doctrine-by-Doctrine Model Comparison", markdown)
        self.assertNotIn("## Behavioral Consistency Index (BCI)", markdown)
        self.assertIn("graphs", json_payload)


if __name__ == "__main__":
    unittest.main()
