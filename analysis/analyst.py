"""
LLM Analyst — optional qualitative layer for OSE analysis reports.

Takes the ReportData dict from AnalysisEngine and produces narrative sections
by feeding statistical summaries + sampled inflection-point reasoning traces
to a single Sonnet call.

This module is OPTIONAL. The report pipeline works without it (engine.py +
renderer.py produce a complete statistical report). The analyst adds:
  - Executive summary (contextualizing the numbers)
  - Turning-point analysis (close-reading of inflection decisions)
  - Cross-doctrine findings (comparative narrative)
  - Escalation dynamics narrative (qualitative interpretation of tension curves)

Design choices:
  - Single LLM call: the model needs full cross-doctrine visibility to make
    comparative claims. Fragmenting across calls produces inconsistent narratives.
  - tool_use output: forces structured JSON rather than free-text, making
    downstream rendering reliable.
  - temperature=0: reproducibility. Same data → same narrative.
  - Traces are SAMPLED (max ~6 per run) by engine.py's _select_inflection_decisions(),
    so the prompt stays within reasonable context limits even with many runs.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any, Dict, Optional

import anthropic
from dotenv import load_dotenv

load_dotenv()

DEFAULT_ANALYST_MODEL = "claude-sonnet-4-6"
ANALYST_MODEL = (
    os.getenv("OSE_ANALYST_MODEL")
    or os.getenv("OSE_ANALYTICS_MODEL")
    or DEFAULT_ANALYST_MODEL
)
MAX_TOKENS = 4096

# ── Analysis output tool schema ──────────────────────────────────────────────

ANALYSIS_TOOL = {
    "name": "submit_analysis",
    "description": (
        "Submit the complete qualitative analysis of the simulation experiment. "
        "All sections must be written in an academic, analytical tone suitable "
        "for a political science research report."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "executive_summary": {
                "type": "string",
                "description": (
                    "2-4 paragraph executive summary. Lead with the headline finding, "
                    "then summarize key differences across doctrine conditions, "
                    "note any surprising patterns, and state the main limitation. "
                    "Written for a reader who will not read the full report."
                ),
            },
            "escalation_dynamics": {
                "type": "string",
                "description": (
                    "2-3 paragraphs interpreting the tension trajectories and "
                    "escalation rates across doctrine conditions. Reference specific "
                    "turns and phase transitions. Explain WHY different doctrines "
                    "produced different escalation patterns, connecting to IR theory."
                ),
            },
            "turning_points": {
                "type": "string",
                "description": (
                    "Analysis of the sampled inflection-point decisions. For each "
                    "notable decision, explain what the actor chose, why (from the "
                    "reasoning trace), and how this reflects or deviates from the "
                    "assigned doctrine. Group by doctrine condition. 3-5 paragraphs."
                ),
            },
            "cross_doctrine_findings": {
                "type": "string",
                "description": (
                    "Unified comparative analysis across all doctrine conditions. "
                    "What behavioral differences did the doctrines produce? Which "
                    "doctrine was most constraining? Where did doctrines fail to "
                    "differentiate behavior? Connect to existing IR literature. "
                    "3-4 paragraphs."
                ),
            },
            "doctrine_model_comparisons": {
                "type": "array",
                "description": (
                    "One entry per doctrine condition comparing how the tested "
                    "provider/model configurations handled that doctrine and how "
                    "confident the analyst is in that comparison."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "doctrine": {
                            "type": "string",
                            "description": "Doctrine condition name.",
                        },
                        "comparison_summary": {
                            "type": "string",
                            "description": (
                                "1-2 paragraphs comparing how different models handled "
                                "this doctrine, citing concrete evidence from the run data."
                            ),
                        },
                        "confidence_score": {
                            "type": "number",
                            "description": (
                                "0.0–1.0 confidence in the comparison, based on sample "
                                "size, separation between models, and clarity of evidence."
                            ),
                        },
                        "confidence_rationale": {
                            "type": "string",
                            "description": (
                                "Short explanation of why the confidence score is low, "
                                "medium, or high."
                            ),
                        },
                    },
                    "required": [
                        "doctrine",
                        "comparison_summary",
                        "confidence_score",
                        "confidence_rationale",
                    ],
                },
            },
            "methodology_notes": {
                "type": "string",
                "description": (
                    "1-2 paragraphs noting any limitations observed in the data: "
                    "small N, action diversity issues, potential confounds, DFS "
                    "or BCI anomalies. Be specific and honest."
                ),
            },
        },
        "required": [
            "executive_summary",
            "escalation_dynamics",
            "turning_points",
            "cross_doctrine_findings",
            "doctrine_model_comparisons",
            "methodology_notes",
        ],
    },
}


# ── Prompt construction ──────────────────────────────────────────────────────

def _build_statistics_block(report_data: Dict[str, Any]) -> str:
    """Render the statistical data into a structured text block for the LLM."""
    meta = report_data["metadata"]
    lines = [
        "# Experiment Statistics",
        "",
        f"**Scenario:** {meta['scenario']}",
        f"**Conditions tested:** {', '.join(meta['conditions'])}",
        f"**Providers tested:** {', '.join(meta.get('providers', ['unknown']))}",
        f"**Models tested:** {', '.join(meta.get('models', ['unknown']))}",
        f"**Total runs:** {meta['total_runs']}",
        f"**Runs per condition:** {json.dumps(meta['runs_per_condition'])}",
        f"**Runs per configuration:** {json.dumps(meta.get('runs_per_configuration', {}))}",
        f"**Max turns per run:** {meta['max_turns']}",
        "",
    ]

    configs = report_data.get("by_configuration", {})
    if configs:
        lines.append("## Configuration Summary")
        for label, stats in configs.items():
            lines.append(f"- {label}")
            lines.append(f"  - Runs: {stats['n_runs']}")
            lines.append(f"  - Outcomes: {json.dumps(stats['outcomes'])}")
            lines.append(
                f"  - Mean final tension: {stats['mean_final_tension']} "
                f"(±{stats['std_final_tension']})"
            )
        lines.append("")

    run_inventory = report_data.get("run_inventory", [])
    if run_inventory:
        lines.append("## Run Inventory")
        for run in run_inventory:
            lines.append(
                f"- {run['run_label']}: outcome={run['outcome']}, "
                f"turns={run['total_turns']}, final_phase={run['final_phase']}, "
                f"final_tension={run['final_tension']}, seed={run.get('seed')}"
            )
        lines.append("")

        for doctrine, stats in report_data["by_doctrine"].items():
            lines.append(f"## Condition: {doctrine}")
            lines.append(f"- Runs: {stats['n_runs']}")
            lines.append(f"- Outcomes: {json.dumps(stats['outcomes'])}")
            lines.append(f"- Outcome probabilities: {json.dumps(stats.get('outcome_probabilities', {}))}")
            lines.append(f"- Mean final tension: {stats['mean_final_tension']} "
                      f"(±{stats['std_final_tension']})")
            lines.append(
                f"- Mean turns to terminal: {stats.get('mean_turns_to_terminal')} "
                f"(±{stats.get('std_turns_to_terminal')})"
            )

            esc = stats["escalation_rate"]
            lines.append(f"- Mean turns to crisis: {esc['mean_turns_to_crisis']}")
            lines.append(f"- Mean turns to war: {esc['mean_turns_to_war']}")
            lines.append(f"- % reaching crisis: {esc['pct_reaching_crisis']}")
            lines.append(f"- % reaching war: {esc['pct_reaching_war']}")

        # Tension trajectory (abbreviated — first, mid, last)
        traj = stats["mean_tension_trajectory"]
        if traj:
            sample_points = []
            indices = [0, len(traj) // 2, len(traj) - 1]
            for i in sorted(set(indices)):
                if i < len(traj):
                    t, mean, std = traj[i]
                    sample_points.append(f"Turn {t}: {mean}±{std}")
            lines.append(f"- Tension trajectory (sample): {', '.join(sample_points)}")

        # Category distribution
        cat_dist = stats.get("aggregate_category_distribution", {})
        if cat_dist:
            cat_str = ", ".join(f"{k}: {v:.1%}" for k, v in sorted(cat_dist.items()))
            lines.append(f"- Action categories: {cat_str}")

        # DFS
        dfs = stats.get("dfs")
        if dfs:
            lines.append(
                f"- DFS: language={dfs['mean_language']}, logic={dfs['mean_logic']}, "
                f"consistency={dfs['consistency_rate']}, "
                f"contamination={dfs['contamination_rate']}"
            )

        lines.append("")

    # BCI
    bci = report_data.get("bci")
    if bci and "summary" in bci:
        lines.append("## Behavioral Consistency Index (BCI)")
        for cond, summary in bci["summary"].items():
            lines.append(
                f"- {cond}: action-level={summary.get('bci_action')}, "
                f"category-level={summary.get('bci_category')}, "
                f"n_runs={summary.get('n_runs')}"
            )
        lines.append("")
    else:
        lines.append("## Behavioral Consistency Index (BCI)")
        lines.append(
            "BCI omitted because the available report data does not contain repeated "
            "runs per doctrine condition."
        )
        lines.append("")

    model_stats = report_data.get("by_model", {})
    if model_stats:
        lines.append("## Model Readiness And Doctrine Separation")
        for label, stats in model_stats.items():
            ops = stats.get("operational_metrics", {})
            separation = stats.get("doctrine_separation") or {}
            lines.append(f"- {label}")
            lines.append(f"  - Doctrines covered: {', '.join(stats.get('doctrines_covered', []))}")
            lines.append(
                f"  - Admission status: {ops.get('admission_status')} | "
                f"valid_rate={ops.get('valid_decision_rate')} | "
                f"skipped_rate={ops.get('skipped_decision_rate')} | "
                f"retry_rate={ops.get('retry_rate')}"
            )
            lines.append(
                f"  - Avg latency ms: {ops.get('avg_latency_ms')} | "
                f"avg total tokens/decision: {ops.get('avg_total_tokens_per_decision')}"
            )
            lines.append(
                f"  - Compatibility strategies: {json.dumps(ops.get('compatibility_strategies', {}))} | "
                f"finish reasons: {json.dumps(ops.get('finish_reasons', {}))}"
            )
            if separation:
                lines.append(
                    f"  - Doctrine separation score={separation.get('score')} | "
                    f"pairwise category distance={separation.get('avg_pairwise_category_distance')} | "
                    f"tension range={separation.get('tension_range')}"
                )
        lines.append("")

    return "\n".join(lines)


def _build_doctrine_model_block(report_data: Dict[str, Any]) -> str:
    """Render per-doctrine model comparisons for the analyst prompt."""
    configs = report_data.get("by_configuration", {})
    if not configs:
        return "# Doctrine-by-Doctrine Model Comparison\n\nNo configuration comparison data available."

    grouped: Dict[str, list[Dict[str, Any]]] = defaultdict(list)
    for stats in configs.values():
        grouped[stats["doctrine"]].append(stats)

    lines = ["# Doctrine-by-Doctrine Model Comparison", ""]
    for doctrine, doctrine_stats in sorted(grouped.items()):
        lines.append(f"## {doctrine}")
        for stats in sorted(doctrine_stats, key=lambda item: (item["provider_name"], item["model_id"])):
            top_categories = ", ".join(
                f"{cat}: {share:.1%}"
                for cat, share in sorted(
                    stats.get("aggregate_category_distribution", {}).items(),
                    key=lambda item: (-item[1], item[0]),
                )[:3]
            ) or "No action data"
            top_actions = ", ".join(
                f"{action}: {count}"
                for action, count in sorted(
                    stats.get("aggregate_action_distribution", {}).items(),
                    key=lambda item: (-item[1], item[0]),
                )[:5]
            ) or "No action data"
            lines.append(
                f"- {stats['provider_name']} / {stats['model_id']}: "
                f"runs={stats['n_runs']}, outcomes={json.dumps(stats['outcomes'])}, "
                f"mean_final_tension={stats['mean_final_tension']}, "
                f"top_categories=[{top_categories}], top_actions=[{top_actions}]"
            )
            dfs = stats.get("dfs")
            if dfs:
                lines.append(
                    f"  DFS: language={dfs['mean_language']}, logic={dfs['mean_logic']}, "
                    f"consistency={dfs['consistency_rate']}, contamination={dfs['contamination_rate']}"
                )
        lines.append("")

    return "\n".join(lines)


def _build_inflections_block(inflections: list) -> str:
    """Render sampled inflection-point decisions for the LLM to analyze."""
    if not inflections:
        return "# Inflection-Point Decisions\n\nNo inflection decisions available for analysis."

    lines = ["# Inflection-Point Decisions", ""]

    for i, dec in enumerate(inflections, 1):
        lines.append(f"## Decision {i}")
        lines.append(f"- **Run:** {dec.get('run_label', dec['run_id'][:12])}")
        lines.append(f"- **Doctrine:** {dec['doctrine']}")
        lines.append(
            f"- **Provider / Model:** {dec.get('provider_name', 'unknown')} / "
            f"{dec.get('model_id', 'unknown')}"
        )
        lines.append(f"- **Actor:** {dec['actor']}")
        lines.append(f"- **Turn:** {dec['turn']}")
        lines.append(f"- **Crisis phase:** {dec['crisis_phase']}")
        lines.append(f"- **Action chosen:** {dec['action_type']}")
        lines.append(f"- **Selection reason:** {dec['selection_reason']}")
        lines.append("")
        lines.append("### Reasoning Trace")
        lines.append("")
        # Truncate very long traces to keep prompt manageable
        trace = dec.get("reasoning_trace", "")
        if len(trace) > 2000:
            trace = trace[:2000] + "\n[... truncated ...]"
        lines.append(trace)
        lines.append("")

    return "\n".join(lines)


# ── Analyst class ────────────────────────────────────────────────────────────

class LLMAnalyst:
    """
    Produces qualitative narrative sections from simulation data.

    Usage:
        analyst = LLMAnalyst()
        sections = analyst.analyze(report_data)
        # sections is a dict with keys matching ANALYSIS_TOOL output schema
    """

    def __init__(self, model: str = ANALYST_MODEL):
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self._model = model

    def analyze(self, report_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Generate qualitative analysis from ReportData.

        Returns a dict with keys: executive_summary, escalation_dynamics,
        turning_points, cross_doctrine_findings, doctrine_model_comparisons,
        methodology_notes.

        Returns None if the LLM call fails.
        """
        stats_block = _build_statistics_block(report_data)
        doctrine_model_block = _build_doctrine_model_block(report_data)
        inflections_block = _build_inflections_block(
            report_data.get("inflection_decisions", [])
        )

        system_prompt = (
            "You are a political science research analyst specializing in "
            "international relations theory and computational modeling. You are "
            "writing the qualitative analysis sections of a research report on "
            "an experiment that tested whether LLM agents produce behaviorally "
            "distinct crisis responses under different IR doctrine conditions "
            "(structural realism, liberal institutionalism, organizational "
            "process model, constructivism, Marxist/radical IR, and a "
            "rational-actor baseline).\n\n"
            "Your analysis must be:\n"
            "- Grounded in the statistical evidence provided\n"
            "- Connected to established IR theory (cite by name, not footnote)\n"
            "- Honest about limitations and small-N caveats\n"
            "- Written in academic prose suitable for a research report\n"
            "- Specific — reference concrete turn numbers, actor names, and metrics\n\n"
            "For doctrine-by-doctrine model comparisons, produce one comparison entry "
            "per doctrine. Compare only the models actually present in the data and "
            "assign confidence conservatively when there is only one run per model.\n\n"
            "Do NOT hallucinate data points. If the statistics are sparse, say so. "
            "If patterns are ambiguous, acknowledge the ambiguity rather than "
            "forcing a narrative."
        )

        user_prompt = (
            f"{stats_block}\n\n---\n\n{doctrine_model_block}\n\n---\n\n"
            f"{inflections_block}\n\n---\n\n"
            "Analyze this simulation experiment data. Call submit_analysis "
            "with your complete qualitative analysis."
        )

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=MAX_TOKENS,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[ANALYSIS_TOOL],
                tool_choice={"type": "any"},
            )

            for block in response.content:
                if block.type == "tool_use" and block.name == "submit_analysis":
                    return block.input

        except Exception as e:
            print(f"[analyst] LLM analysis failed: {e}")

        return None
