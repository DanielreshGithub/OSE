"""
Report Renderer — converts ReportData into Markdown or LaTeX output.

Takes the dict from AnalysisEngine.analyze() plus optional qualitative
sections from LLMAnalyst.analyze() and produces a formatted research report.

Two output modes:
  - Markdown: self-contained .md suitable for Obsidian / GitHub rendering
  - LaTeX: matches the existing OSE research document style (booktabs,
    graybox environment, fancyhdr, natbib, lmodern)

Report sections (in order):
  1. Executive Summary (LLM if available, else templated)
  2. Experiment Overview (metadata table)
  3. Outcome Distribution
  4. Escalation Dynamics (tension trajectory, phase transitions)
  5. Action Distribution (per-actor frequency, category breakdown)
  6. Doctrine Fidelity (DFS scores if available)
  7. Behavioral Consistency (BCI if multiple runs)
  8. Key Turning Points (LLM-analyzed inflection decisions, --llm only)
  9. Cross-Doctrine Findings (LLM if available)
  10. Limitations
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


# ── Markdown Renderer ────────────────────────────────────────────────────────

class MarkdownRenderer:
    """Renders ReportData + optional analyst output to Markdown."""

    def render(
        self,
        data: Dict[str, Any],
        analyst: Optional[Dict[str, str]] = None,
    ) -> str:
        sections = [
            self._title(data),
            self._executive_summary(data, analyst),
            self._experiment_overview(data),
            self._visual_summary(data),
            self._configuration_summary(data),
            self._doctrine_model_comparison(data, analyst),
            self._run_inventory(data),
            self._outcome_distribution(data),
            self._escalation_dynamics(data, analyst),
            self._action_distribution(data),
            self._doctrine_fidelity(data),
            self._behavioral_consistency(data),
            self._turning_points(data, analyst),
            self._cross_doctrine_findings(analyst),
            self._limitations(data, analyst),
            self._footer(data),
        ]
        return "\n\n".join(s for s in sections if s)

    def _title(self, data: Dict) -> str:
        meta = data["metadata"]
        return (
            f"# OSE Experiment Report: {meta['scenario']}\n\n"
            f"**Generated:** {meta['generated_at'][:19]}  \n"
            f"**Conditions:** {', '.join(meta['conditions'])}  \n"
            f"**Providers:** {', '.join(meta.get('providers', ['unknown']))}  \n"
            f"**Models:** {', '.join(meta.get('models', ['unknown']))}  \n"
            f"**Total runs:** {meta['total_runs']}  \n"
            f"**Max turns:** {meta['max_turns']}"
        )

    def _visual_summary(self, data: Dict) -> str:
        graphs = data.get("graphs", [])
        if not graphs:
            return ""

        lines = ["## Visual Summary\n"]
        for graph in graphs:
            title = graph.get("title", "Chart")
            lines.append(f"### {title}\n")
            lines.append(f"![{title}]({graph['relative_path']})")
            lines.append("")
        return "\n".join(lines).strip()

    def _executive_summary(self, data: Dict, analyst: Optional[Dict]) -> str:
        if analyst and analyst.get("executive_summary"):
            return f"## Executive Summary\n\n{analyst['executive_summary']}"

        # Templated fallback
        meta = data["metadata"]
        conditions = meta["conditions"]
        bd = data["by_doctrine"]

        lines = ["## Executive Summary\n"]
        lines.append(
            f"This report summarizes {meta['total_runs']} simulation runs "
            f"of the **{meta['scenario']}** scenario across "
            f"{len(conditions)} doctrine conditions: "
            f"{', '.join(conditions)}."
        )

        # Headline comparison: which condition had highest/lowest final tension
        if len(bd) >= 2:
            sorted_docs = sorted(bd.items(), key=lambda x: x[1]["mean_final_tension"])
            lowest = sorted_docs[0]
            highest = sorted_docs[-1]
            lines.append(
                f"\nThe **{lowest[0]}** condition produced the lowest mean final tension "
                f"({lowest[1]['mean_final_tension']}), while **{highest[0]}** produced "
                f"the highest ({highest[1]['mean_final_tension']})."
            )

        return "\n".join(lines)

    def _experiment_overview(self, data: Dict) -> str:
        meta = data["metadata"]
        rows = []
        for cond in meta["conditions"]:
            n = meta["runs_per_condition"].get(cond, 0)
            stats = data["by_doctrine"].get(cond, {})
            outcomes = stats.get("outcomes", {})
            outcome_str = ", ".join(f"{k}: {v}" for k, v in outcomes.items())
            rows.append(f"| {cond} | {n} | {outcome_str} |")

        lines = [
            "## Experiment Overview\n",
            f"**Providers:** {', '.join(meta.get('providers', ['unknown']))}  ",
            f"**Models:** {', '.join(meta.get('models', ['unknown']))}  ",
        ]
        if meta.get("mixed_model_report"):
            lines.append(
                "_This report mixes multiple provider/model configurations. "
                "Use Configuration Summary and Run Inventory to see which model produced which run._"
            )
        lines.append(
            "| Condition | Runs | Outcomes |\n"
            "|-----------|------|----------|\n"
            + "\n".join(rows)
        )
        return "\n".join(lines)

    def _configuration_summary(self, data: Dict) -> str:
        configs = data.get("by_configuration", {})
        if not configs:
            return ""

        lines = ["## Configuration Summary\n"]
        lines.append("| Doctrine | Provider | Model | Runs | Mean Final Tension | Outcomes |")
        lines.append("|----------|----------|-------|------|--------------------|----------|")
        for stats in configs.values():
            outcome_str = ", ".join(
                f"{k}: {v}" for k, v in stats.get("outcomes", {}).items()
            )
            lines.append(
                f"| {stats['doctrine']} | {stats['provider_name']} | {stats['model_id']} | "
                f"{stats['n_runs']} | {stats['mean_final_tension']:.3f} | {outcome_str} |"
            )
        return "\n".join(lines)

    def _run_inventory(self, data: Dict) -> str:
        runs = data.get("run_inventory", [])
        if not runs:
            return ""

        lines = ["## Run Inventory\n"]
        lines.append("| Run ID | Doctrine | Provider | Model | Seed | Turns | Outcome | Final Phase | Final Tension |")
        lines.append("|--------|----------|----------|-------|------|-------|---------|-------------|---------------|")
        for run in runs:
            lines.append(
                f"| {run['run_id']} | {run['doctrine']} | {run['provider_name']} | "
                f"{run['model_id']} | {run.get('seed', '—')} | {run['total_turns']} | "
                f"{run['outcome']} | {run['final_phase']} | {run['final_tension']:.3f} |"
            )
        return "\n".join(lines)

    def _doctrine_model_comparison(self, data: Dict, analyst: Optional[Dict]) -> str:
        grouped = _group_configurations_by_doctrine(data)
        if not grouped:
            return ""

        analyst_entries = {}
        if analyst and analyst.get("doctrine_model_comparisons"):
            analyst_entries = {
                entry["doctrine"]: entry
                for entry in analyst["doctrine_model_comparisons"]
            }

        lines = ["## Doctrine-by-Doctrine Model Comparison\n"]

        for doctrine in data["metadata"]["conditions"]:
            doctrine_configs = grouped.get(doctrine, [])
            if not doctrine_configs:
                continue

            lines.append(f"### {doctrine}\n")
            analyst_entry = analyst_entries.get(doctrine)
            if analyst_entry:
                confidence = max(0.0, min(1.0, float(analyst_entry.get("confidence_score", 0.0))))
                lines.append(analyst_entry["comparison_summary"])
                lines.append("")
                lines.append(
                    f"**Confidence:** {_confidence_label(confidence)} ({confidence:.0%})  \n"
                    f"{analyst_entry['confidence_rationale']}"
                )
                lines.append("")
            else:
                confidence, rationale = _estimate_confidence(doctrine_configs)
                lines.append(
                    "Fallback comparison generated from observed outcome, tension, "
                    "and action-mix differences across configurations."
                )
                lines.append("")
                lines.append(
                    f"**Confidence:** {_confidence_label(confidence)} ({confidence:.0%})  \n"
                    f"{rationale}"
                )
                lines.append("")

            lines.append("| Provider | Model | Runs | Outcome(s) | Final Tension | Top Categories | DFS Logic |")
            lines.append("|----------|-------|------|------------|---------------|----------------|-----------|")
            for stat in doctrine_configs:
                outcome_str = ", ".join(
                    f"{outcome}:{count}" for outcome, count in sorted(stat.get("outcomes", {}).items())
                )
                dfs = stat.get("dfs")
                dfs_logic = f"{dfs['mean_logic']:.3f}" if dfs else "—"
                lines.append(
                    f"| {stat['provider_name']} | {stat['model_id']} | {stat['n_runs']} | "
                    f"{outcome_str or '—'} | {stat['mean_final_tension']:.3f} | "
                    f"{_top_categories(stat)} | {dfs_logic} |"
                )
            lines.append("")

        return "\n".join(lines).strip()

    def _outcome_distribution(self, data: Dict) -> str:
        bd = data["by_doctrine"]
        if not bd:
            return ""

        # Collect all unique outcomes
        all_outcomes = set()
        for stats in bd.values():
            all_outcomes.update(stats.get("outcomes", {}).keys())
        all_outcomes = sorted(all_outcomes)

        if not all_outcomes:
            return ""

        header = "| Condition | " + " | ".join(all_outcomes) + " |"
        sep = "|-----------|" + "|".join("---" for _ in all_outcomes) + "|"

        rows = []
        for doctrine, stats in bd.items():
            outcomes = stats.get("outcomes", {})
            cells = [str(outcomes.get(o, 0)) for o in all_outcomes]
            rows.append(f"| {doctrine} | " + " | ".join(cells) + " |")

        return (
            "## Outcome Distribution\n\n"
            + header + "\n" + sep + "\n"
            + "\n".join(rows)
        )

    def _escalation_dynamics(self, data: Dict, analyst: Optional[Dict]) -> str:
        lines = ["## Escalation Dynamics\n"]

        # Escalation rate table
        lines.append("### Escalation Rates\n")
        lines.append("| Condition | Mean Turns to Crisis | Mean Turns to War | % Reaching Crisis | % Reaching War |")
        lines.append("|-----------|---------------------|-------------------|-------------------|----------------|")

        for doctrine, stats in data["by_doctrine"].items():
            esc = stats["escalation_rate"]
            ttc = esc["mean_turns_to_crisis"]
            ttw = esc["mean_turns_to_war"]
            pc = esc["pct_reaching_crisis"]
            pw = esc["pct_reaching_war"]
            lines.append(
                f"| {doctrine} | {ttc if ttc is not None else 'N/A'} | "
                f"{ttw if ttw is not None else 'N/A'} | "
                f"{pc:.1%} | {pw:.1%} |"
            )

        # Tension trajectory table
        lines.append("\n### Mean Tension Trajectory\n")
        lines.append("| Turn | " + " | ".join(
            f"{d} (mean±std)" for d in data["by_doctrine"]
        ) + " |")
        lines.append("|------|" + "|".join(
            "---" for _ in data["by_doctrine"]
        ) + "|")

        # Merge trajectories across doctrines
        all_turns = set()
        for stats in data["by_doctrine"].values():
            for t, _, _ in stats["mean_tension_trajectory"]:
                all_turns.add(t)

        traj_by_doctrine = {}
        for doctrine, stats in data["by_doctrine"].items():
            traj_by_doctrine[doctrine] = {
                t: (m, s) for t, m, s in stats["mean_tension_trajectory"]
            }

        for turn in sorted(all_turns):
            cells = []
            for doctrine in data["by_doctrine"]:
                entry = traj_by_doctrine.get(doctrine, {}).get(turn)
                if entry:
                    cells.append(f"{entry[0]:.3f}±{entry[1]:.3f}")
                else:
                    cells.append("—")
            lines.append(f"| {turn} | " + " | ".join(cells) + " |")

        # LLM narrative if available
        if analyst and analyst.get("escalation_dynamics"):
            lines.append(f"\n### Interpretation\n\n{analyst['escalation_dynamics']}")

        return "\n".join(lines)

    def _action_distribution(self, data: Dict) -> str:
        lines = ["## Action Distribution\n"]

        for doctrine, stats in data["by_doctrine"].items():
            lines.append(f"### {doctrine}\n")

            # Category-level breakdown
            cat_dist = stats.get("aggregate_category_distribution", {})
            if cat_dist:
                lines.append("**Action categories (all actors):**\n")
                lines.append("| Category | Fraction |")
                lines.append("|----------|----------|")
                for cat, frac in sorted(cat_dist.items(), key=lambda x: -x[1]):
                    lines.append(f"| {cat} | {frac:.1%} |")
                lines.append("")

            # Per-actor top actions
            action_dist = stats.get("action_distribution", {})
            if action_dist:
                lines.append("**Top actions by actor:**\n")
                for actor, actions in action_dist.items():
                    top = sorted(actions.items(), key=lambda x: -x[1])[:5]
                    action_str = ", ".join(f"{a} ({c})" for a, c in top)
                    lines.append(f"- **{actor}:** {action_str}")
                lines.append("")

        return "\n".join(lines)

    def _doctrine_fidelity(self, data: Dict) -> str:
        has_dfs = any(
            stats.get("dfs") is not None
            for stats in data["by_doctrine"].values()
        )
        if not has_dfs:
            return ""

        lines = ["## Doctrine Fidelity Scores (DFS)\n"]
        lines.append("| Condition | Language | Logic | Consistency | Contamination |")
        lines.append("|-----------|---------|-------|-------------|---------------|")

        for doctrine, stats in data["by_doctrine"].items():
            dfs = stats.get("dfs")
            if dfs:
                lines.append(
                    f"| {doctrine} | {dfs['mean_language']:.3f} | "
                    f"{dfs['mean_logic']:.3f} | "
                    f"{dfs['consistency_rate']:.1%} | "
                    f"{dfs['contamination_rate']:.1%} |"
                )
            else:
                lines.append(f"| {doctrine} | — | — | — | — |")

        return "\n".join(lines)

    def _behavioral_consistency(self, data: Dict) -> str:
        bci = data.get("bci")
        if not bci or "summary" not in bci:
            return ""

        lines = ["## Behavioral Consistency Index (BCI)\n"]
        lines.append(
            "BCI measures action distribution variance across repeated runs. "
            "Low BCI (→0) indicates the doctrine reliably channels behavior; "
            "high BCI (→1) indicates stochastic behavior despite prescription.\n"
        )
        lines.append("| Condition | BCI (Action) | BCI (Category) | Runs |")
        lines.append("|-----------|-------------|----------------|------|")

        for cond, summary in bci["summary"].items():
            ba = summary.get("bci_action")
            bc = summary.get("bci_category")
            lines.append(
                f"| {cond} | {ba if ba is not None else '—'} | "
                f"{bc if bc is not None else '—'} | {summary.get('n_runs', '—')} |"
            )

        return "\n".join(lines)

    def _turning_points(self, data: Dict, analyst: Optional[Dict]) -> str:
        inflections = data.get("inflection_decisions", [])
        if not inflections:
            return ""

        lines = ["## Key Turning Points\n"]

        if analyst and analyst.get("turning_points"):
            lines.append(analyst["turning_points"])
        else:
            # Structured fallback — list inflection decisions without LLM interpretation
            for dec in inflections:
                lines.append(
                    f"- **Turn {dec['turn']}** ({dec['doctrine']}, {dec['provider_name']}, "
                    f"{dec['model_id']}, {dec['actor']}, {dec.get('run_label', dec['run_id'])}): "
                    f"`{dec['action_type']}` — {dec['selection_reason']}"
                )

        return "\n".join(lines)

    def _cross_doctrine_findings(self, analyst: Optional[Dict]) -> str:
        if not analyst or not analyst.get("cross_doctrine_findings"):
            return ""
        return (
            "## Cross-Doctrine Findings\n\n"
            + analyst["cross_doctrine_findings"]
        )

    def _limitations(self, data: Dict, analyst: Optional[Dict]) -> str:
        lines = ["## Limitations\n"]

        if analyst and analyst.get("methodology_notes"):
            lines.append(analyst["methodology_notes"])
        else:
            meta = data["metadata"]
            lines.append(
                f"This analysis is based on {meta['total_runs']} total runs. "
                "Small sample sizes limit statistical power and the generalizability "
                "of observed patterns. Action distributions may reflect the "
                "available action space constraints as much as doctrine effects. "
                "LLM behavior is sensitive to prompt engineering and model version; "
                "results should be interpreted as indicative rather than definitive."
            )

        return "\n".join(lines)

    def _footer(self, data: Dict) -> str:
        return (
            "---\n\n"
            f"*Report generated by OSE Analysis Engine at "
            f"{data['metadata']['generated_at'][:19]}*"
        )


def _group_configurations_by_doctrine(data: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for stats in data.get("by_configuration", {}).values():
        grouped[stats["doctrine"]].append(stats)
    for doctrine, configs in grouped.items():
        grouped[doctrine] = sorted(configs, key=lambda item: (item["provider_name"], item["model_id"]))
    return dict(grouped)


def _top_categories(stats: Dict[str, Any], limit: int = 3) -> str:
    categories = sorted(
        stats.get("aggregate_category_distribution", {}).items(),
        key=lambda item: (-item[1], item[0]),
    )[:limit]
    if not categories:
        return "—"
    return ", ".join(f"{name}:{share:.0%}" for name, share in categories)


def _estimate_confidence(configs: List[Dict[str, Any]]) -> Tuple[float, str]:
    if len(configs) <= 1:
        return 0.2, "Only one configuration was available for this doctrine, so comparative confidence is necessarily low."

    tensions = [float(stat["mean_final_tension"]) for stat in configs]
    spread = max(tensions) - min(tensions)
    unique_outcomes = {
        outcome
        for stat in configs
        for outcome in stat.get("outcomes", {}).keys()
    }
    top_category_sets = {
        tuple(
            name for name, _ in sorted(
                stat.get("aggregate_category_distribution", {}).items(),
                key=lambda item: (-item[1], item[0]),
            )[:2]
        )
        for stat in configs
    }

    score = 0.25
    if len(configs) >= 3:
        score += 0.1
    if spread >= 0.2:
        score += 0.25
    elif spread >= 0.1:
        score += 0.15
    elif spread >= 0.05:
        score += 0.08
    if len(unique_outcomes) >= 2:
        score += 0.15
    if len(top_category_sets) >= 2:
        score += 0.12

    score = min(score, 0.75)
    rationale = (
        f"Confidence is capped because each provider/model contributes only {configs[0]['n_runs']} run(s) here. "
        f"Observed final-tension spread is {spread:.3f}; outcome diversity={len(unique_outcomes)}; "
        f"distinct top-category patterns={len(top_category_sets)}."
    )
    return score, rationale


def _confidence_label(score: float) -> str:
    if score >= 0.67:
        return "High"
    if score >= 0.4:
        return "Medium"
    return "Low"


# ── LaTeX Renderer ───────────────────────────────────────────────────────────

class LaTeXRenderer:
    """
    Renders ReportData + optional analyst output to LaTeX.

    Matches the style of the existing OSE research document:
    booktabs tables, graybox environment, fancyhdr, natbib, lmodern.
    """

    def render(
        self,
        data: Dict[str, Any],
        analyst: Optional[Dict[str, str]] = None,
    ) -> str:
        sections = [
            self._preamble(data),
            self._begin_document(data),
            self._executive_summary(data, analyst),
            self._experiment_overview(data),
            self._configuration_summary(data),
            self._doctrine_model_comparison(data, analyst),
            self._run_inventory(data),
            self._outcome_distribution(data),
            self._escalation_dynamics(data, analyst),
            self._action_distribution(data),
            self._doctrine_fidelity(data),
            self._behavioral_consistency(data),
            self._turning_points(data, analyst),
            self._cross_doctrine_findings(analyst),
            self._limitations(data, analyst),
            self._end_document(),
        ]
        return "\n\n".join(s for s in sections if s)

    def _preamble(self, data: Dict) -> str:
        return r"""\documentclass[12pt, a4paper]{article}

% --- Packages ---
\usepackage[margin=2.5cm]{geometry}
\usepackage{setspace}
\usepackage{titlesec}
\usepackage{hyperref}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{parskip}
\usepackage{graphicx}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage{xcolor}
\usepackage{amsmath}
\usepackage{microtype}
\usepackage{natbib}
\usepackage[T1]{fontenc}
\usepackage{lmodern}

% --- Hyperref Config ---
\hypersetup{
    colorlinks=true,
    linkcolor=black,
    citecolor=black,
    urlcolor=blue,
    pdftitle={OSE Experiment Report},
    pdfauthor={Daniel Reshetnikov},
}

% --- Page Style ---
\pagestyle{fancy}
\fancyhf{}
\rhead{\small OSE Experiment Report}
\lhead{\small Omni-Simulation Engine}
\cfoot{\thepage}
\renewcommand{\headrulewidth}{0.4pt}

% --- Section Formatting ---
\titleformat{\section}{\large\bfseries}{}{0em}{}[\titlerule]
\titleformat{\subsection}{\normalsize\bfseries}{}{0em}{}
\titleformat{\subsubsection}{\normalsize\itshape}{}{0em}{}

% --- Box Environment ---
\newenvironment{graybox}{%
  \vspace{10pt}%
  \begin{center}%
  \begin{minipage}{0.92\textwidth}%
  \noindent\rule{\textwidth}{0.4pt}\\[4pt]%
}{%
  \\[4pt]\noindent\rule{\textwidth}{0.4pt}%
  \end{minipage}%
  \end{center}%
  \vspace{10pt}%
}

% --- Spacing ---
\onehalfspacing
\setlength{\parindent}{0pt}
\setlength{\parskip}{8pt}"""

    def _begin_document(self, data: Dict) -> str:
        meta = data["metadata"]
        scenario = _tex_escape(meta["scenario"])
        conditions = ", ".join(_tex_escape(c) for c in meta["conditions"])
        return rf"""\begin{{document}}

\begin{{titlepage}}
\centering
\vspace*{{3cm}}

{{\Huge\bfseries OSE Experiment Report}}\\[0.5cm]
{{\Large\bfseries {scenario}}}\\[1cm]
{{\large Doctrine Conditions: {conditions}}}\\[0.3cm]
{{\large {meta['total_runs']} Runs, {meta['max_turns']} Max Turns}}\\[2cm]

{{\large Daniel Reshetnikov}}\\[0.3cm]
{{\normalsize Independent Research}}\\[0.3cm]
{{\normalsize {datetime.utcnow().strftime('%B %Y')}}}

\vfill
{{\small Generated by OSE Analysis Engine}}
\end{{titlepage}}

\tableofcontents
\newpage"""

    def _executive_summary(self, data: Dict, analyst: Optional[Dict]) -> str:
        lines = [r"\section{Executive Summary}", ""]

        if analyst and analyst.get("executive_summary"):
            lines.append(_tex_escape(analyst["executive_summary"]))
        else:
            meta = data["metadata"]
            conditions = ", ".join(_tex_escape(c) for c in meta["conditions"])
            lines.append(
                f"This report summarizes {meta['total_runs']} simulation runs "
                f"of the \\textbf{{{_tex_escape(meta['scenario'])}}} scenario "
                f"across {len(meta['conditions'])} doctrine conditions: {conditions}."
            )

            bd = data["by_doctrine"]
            if len(bd) >= 2:
                sorted_docs = sorted(bd.items(), key=lambda x: x[1]["mean_final_tension"])
                lowest = sorted_docs[0]
                highest = sorted_docs[-1]
                lines.append(
                    f"\nThe \\textbf{{{_tex_escape(lowest[0])}}} condition produced "
                    f"the lowest mean final tension ({lowest[1]['mean_final_tension']}), "
                    f"while \\textbf{{{_tex_escape(highest[0])}}} produced the highest "
                    f"({highest[1]['mean_final_tension']})."
                )

        return "\n".join(lines)

    def _experiment_overview(self, data: Dict) -> str:
        meta = data["metadata"]
        rows = []
        for cond in meta["conditions"]:
            n = meta["runs_per_condition"].get(cond, 0)
            stats = data["by_doctrine"].get(cond, {})
            outcomes = stats.get("outcomes", {})
            outcome_str = ", ".join(f"{k}: {v}" for k, v in outcomes.items())
            rows.append(
                f"        {_tex_escape(cond)} & {n} & {_tex_escape(outcome_str)} \\\\"
            )

        parts = []
        if meta.get("mixed_model_report"):
            parts.append(
                r"\begin{graybox}"
                "\n"
                r"\textbf{Note:} This report mixes multiple provider/model configurations. "
                r"Use the configuration and run inventory sections to identify which model "
                r"produced which run."
                "\n"
                r"\end{graybox}"
            )

        parts.append(
            r"\section{Experiment Overview}" + "\n\n"
            + f"Providers: {_tex_escape(', '.join(meta.get('providers', ['unknown'])))}\\\\\n"
            + f"Models: {_tex_escape(', '.join(meta.get('models', ['unknown'])))}\n\n"
            + r"\begin{table}[h]" + "\n"
            + r"\centering" + "\n"
            + r"\begin{tabular}{lrl}" + "\n"
            + r"    \toprule" + "\n"
            + r"    Condition & Runs & Outcomes \\" + "\n"
            + r"    \midrule" + "\n"
            + "\n".join(rows) + "\n"
            + r"    \bottomrule" + "\n"
            + r"\end{tabular}" + "\n"
            + r"\caption{Experiment configuration and outcomes.}" + "\n"
            + r"\end{table}"
        )

        return "\n\n".join(parts)

    def _configuration_summary(self, data: Dict) -> str:
        configs = data.get("by_configuration", {})
        if not configs:
            return ""

        rows = []
        for stats in configs.values():
            outcome_str = ", ".join(
                f"{k}: {v}" for k, v in stats.get("outcomes", {}).items()
            )
            rows.append(
                "        "
                f"{_tex_escape(stats['doctrine'])} & "
                f"{_tex_escape(stats['provider_name'])} & "
                f"{_tex_escape(stats['model_id'])} & "
                f"{stats['n_runs']} & "
                f"{stats['mean_final_tension']:.3f} & "
                f"{_tex_escape(outcome_str)} \\\\"
            )

        return (
            r"\section{Configuration Summary}" + "\n\n"
            r"\begin{longtable}{lllrrl}" + "\n"
            r"    \toprule" + "\n"
            r"    Doctrine & Provider & Model & Runs & Mean Final Tension & Outcomes \\" + "\n"
            r"    \midrule" + "\n"
            r"    \endhead" + "\n"
            + "\n".join(rows) + "\n"
            r"    \bottomrule" + "\n"
            r"\end{longtable}"
        )

    def _doctrine_model_comparison(self, data: Dict, analyst: Optional[Dict]) -> str:
        grouped = _group_configurations_by_doctrine(data)
        if not grouped:
            return ""

        analyst_entries = {}
        if analyst and analyst.get("doctrine_model_comparisons"):
            analyst_entries = {
                entry["doctrine"]: entry
                for entry in analyst["doctrine_model_comparisons"]
            }

        parts = [r"\section{Doctrine-by-Doctrine Model Comparison}"]

        for doctrine in data["metadata"]["conditions"]:
            doctrine_configs = grouped.get(doctrine, [])
            if not doctrine_configs:
                continue

            parts.append(rf"\subsection{{{_tex_escape(doctrine)}}}")
            analyst_entry = analyst_entries.get(doctrine)
            if analyst_entry:
                confidence = max(0.0, min(1.0, float(analyst_entry.get("confidence_score", 0.0))))
                parts.append(_tex_escape(analyst_entry["comparison_summary"]))
                parts.append(
                    rf"\textbf{{Confidence:}} {_tex_escape(_confidence_label(confidence))} "
                    rf"({confidence:.0%})\\"
                )
                parts.append(_tex_escape(analyst_entry["confidence_rationale"]))
            else:
                confidence, rationale = _estimate_confidence(doctrine_configs)
                parts.append(_tex_escape(
                    "Fallback comparison generated from observed outcome, tension, "
                    "and action-mix differences across configurations."
                ))
                parts.append(
                    rf"\textbf{{Confidence:}} {_tex_escape(_confidence_label(confidence))} "
                    rf"({confidence:.0%})\\"
                )
                parts.append(_tex_escape(rationale))

            rows = []
            for stat in doctrine_configs:
                outcome_str = ", ".join(
                    f"{outcome}:{count}" for outcome, count in sorted(stat.get("outcomes", {}).items())
                )
                dfs = stat.get("dfs")
                dfs_logic = f"{dfs['mean_logic']:.3f}" if dfs else "---"
                rows.append(
                    "        "
                    f"{_tex_escape(stat['provider_name'])} & "
                    f"{_tex_escape(stat['model_id'])} & "
                    f"{stat['n_runs']} & "
                    f"{_tex_escape(outcome_str or '---')} & "
                    f"{stat['mean_final_tension']:.3f} & "
                    f"{_tex_escape(_top_categories(stat))} & "
                    f"{_tex_escape(dfs_logic)} \\\\"
                )

            parts.append(
                r"\begin{longtable}{llrllll}" + "\n"
                r"    \toprule" + "\n"
                r"    Provider & Model & Runs & Outcome(s) & Final Tension & Top Categories & DFS Logic \\" + "\n"
                r"    \midrule" + "\n"
                r"    \endhead" + "\n"
                + "\n".join(rows) + "\n"
                + r"    \bottomrule" + "\n"
                + r"\end{longtable}"
            )

        return "\n\n".join(parts)

    def _run_inventory(self, data: Dict) -> str:
        runs = data.get("run_inventory", [])
        if not runs:
            return ""

        rows = []
        for run in runs:
            seed = run.get("seed")
            rows.append(
                "        "
                f"{_tex_escape(run['run_id'])} & "
                f"{_tex_escape(run['doctrine'])} & "
                f"{_tex_escape(run['provider_name'])} & "
                f"{_tex_escape(run['model_id'])} & "
                f"{seed if seed is not None else '---'} & "
                f"{run['total_turns']} & "
                f"{_tex_escape(run['outcome'])} & "
                f"{_tex_escape(run['final_phase'])} & "
                f"{run['final_tension']:.3f} \\\\"
            )

        return (
            r"\section{Run Inventory}" + "\n\n"
            r"\begin{longtable}{llllrrlll}" + "\n"
            r"    \toprule" + "\n"
            r"    Run ID & Doctrine & Provider & Model & Seed & Turns & Outcome & Final Phase & Final Tension \\" + "\n"
            r"    \midrule" + "\n"
            r"    \endhead" + "\n"
            + "\n".join(rows) + "\n"
            r"    \bottomrule" + "\n"
            r"\end{longtable}"
        )

    def _outcome_distribution(self, data: Dict) -> str:
        bd = data["by_doctrine"]
        all_outcomes = set()
        for stats in bd.values():
            all_outcomes.update(stats.get("outcomes", {}).keys())
        all_outcomes = sorted(all_outcomes)

        if not all_outcomes:
            return ""

        col_spec = "l" + "r" * len(all_outcomes)
        header = " & ".join(_tex_escape(o) for o in all_outcomes)

        rows = []
        for doctrine, stats in bd.items():
            outcomes = stats.get("outcomes", {})
            cells = [str(outcomes.get(o, 0)) for o in all_outcomes]
            rows.append(f"        {_tex_escape(doctrine)} & " + " & ".join(cells) + r" \\")

        return (
            r"\section{Outcome Distribution}" + "\n\n"
            r"\begin{table}[h]" + "\n"
            r"\centering" + "\n"
            rf"\begin{{tabular}}{{{col_spec}}}" + "\n"
            r"    \toprule" + "\n"
            f"    Condition & {header} \\\\\n"
            r"    \midrule" + "\n"
            + "\n".join(rows) + "\n"
            r"    \bottomrule" + "\n"
            r"\end{tabular}" + "\n"
            r"\caption{Outcome distribution by doctrine condition.}" + "\n"
            r"\end{table}"
        )

    def _escalation_dynamics(self, data: Dict, analyst: Optional[Dict]) -> str:
        lines = [r"\section{Escalation Dynamics}", ""]

        # Escalation rate table
        lines.append(r"\subsection{Escalation Rates}")
        lines.append("")
        lines.append(r"\begin{table}[h]")
        lines.append(r"\centering")
        lines.append(r"\begin{tabular}{lrrrr}")
        lines.append(r"    \toprule")
        lines.append(r"    Condition & Turns to Crisis & Turns to War & \% Crisis & \% War \\")
        lines.append(r"    \midrule")

        for doctrine, stats in data["by_doctrine"].items():
            esc = stats["escalation_rate"]
            ttc = esc["mean_turns_to_crisis"]
            ttw = esc["mean_turns_to_war"]
            pc = esc["pct_reaching_crisis"]
            pw = esc["pct_reaching_war"]
            lines.append(
                f"        {_tex_escape(doctrine)} & "
                f"{ttc if ttc is not None else '---'} & "
                f"{ttw if ttw is not None else '---'} & "
                f"{_tex_pct(pc)} & {_tex_pct(pw)} \\\\"
            )

        lines.append(r"    \bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\caption{Mean escalation rates by doctrine condition.}")
        lines.append(r"\end{table}")

        # Tension trajectory table
        lines.append("")
        lines.append(r"\subsection{Mean Tension Trajectory}")
        lines.append("")

        doctrines = list(data["by_doctrine"].keys())
        n_cols = len(doctrines)
        col_spec = "r" + "r" * n_cols
        header = " & ".join(_tex_escape(d) for d in doctrines)

        all_turns = set()
        for stats in data["by_doctrine"].values():
            for t, _, _ in stats["mean_tension_trajectory"]:
                all_turns.add(t)

        traj_by_doctrine = {}
        for doctrine, stats in data["by_doctrine"].items():
            traj_by_doctrine[doctrine] = {
                t: (m, s) for t, m, s in stats["mean_tension_trajectory"]
            }

        lines.append(r"\begin{longtable}{" + col_spec + "}")
        lines.append(r"    \toprule")
        lines.append(f"    Turn & {header} \\\\")
        lines.append(r"    \midrule")
        lines.append(r"    \endhead")

        for turn in sorted(all_turns):
            cells = []
            for doctrine in doctrines:
                entry = traj_by_doctrine.get(doctrine, {}).get(turn)
                if entry:
                    cells.append(f"${entry[0]:.3f} \\pm {entry[1]:.3f}$")
                else:
                    cells.append("---")
            lines.append(f"    {turn} & " + " & ".join(cells) + r" \\")

        lines.append(r"    \bottomrule")
        lines.append(r"\end{longtable}")

        # LLM narrative
        if analyst and analyst.get("escalation_dynamics"):
            lines.append("")
            lines.append(r"\subsection{Interpretation}")
            lines.append("")
            lines.append(_tex_escape(analyst["escalation_dynamics"]))

        return "\n".join(lines)

    def _action_distribution(self, data: Dict) -> str:
        lines = [r"\section{Action Distribution}", ""]

        for doctrine, stats in data["by_doctrine"].items():
            lines.append(rf"\subsection{{{_tex_escape(doctrine)}}}")

            cat_dist = stats.get("aggregate_category_distribution", {})
            if cat_dist:
                lines.append("")
                lines.append(r"\begin{table}[h]")
                lines.append(r"\centering")
                lines.append(r"\begin{tabular}{lr}")
                lines.append(r"    \toprule")
                lines.append(r"    Category & Fraction \\")
                lines.append(r"    \midrule")
                for cat, frac in sorted(cat_dist.items(), key=lambda x: -x[1]):
                    lines.append(f"    {_tex_escape(cat)} & {_tex_pct(frac)} \\\\")
                lines.append(r"    \bottomrule")
                lines.append(r"\end{tabular}")
                lines.append(rf"\caption{{Action categories for {_tex_escape(doctrine)}.}}")
                lines.append(r"\end{table}")

            action_dist = stats.get("action_distribution", {})
            if action_dist:
                lines.append("")
                for actor, actions in action_dist.items():
                    top = sorted(actions.items(), key=lambda x: -x[1])[:5]
                    action_str = ", ".join(
                        f"{_tex_escape(a)} ({c})" for a, c in top
                    )
                    lines.append(
                        rf"\textbf{{{_tex_escape(actor)}:}} {action_str}"
                    )
                    lines.append("")

        return "\n".join(lines)

    def _doctrine_fidelity(self, data: Dict) -> str:
        has_dfs = any(
            stats.get("dfs") is not None
            for stats in data["by_doctrine"].values()
        )
        if not has_dfs:
            return ""

        lines = [r"\section{Doctrine Fidelity Scores (DFS)}", ""]
        lines.append(r"\begin{table}[h]")
        lines.append(r"\centering")
        lines.append(r"\begin{tabular}{lrrrr}")
        lines.append(r"    \toprule")
        lines.append(r"    Condition & Language & Logic & Consistency & Contamination \\")
        lines.append(r"    \midrule")

        for doctrine, stats in data["by_doctrine"].items():
            dfs = stats.get("dfs")
            if dfs:
                lines.append(
                    f"    {_tex_escape(doctrine)} & {dfs['mean_language']:.3f} & "
                    f"{dfs['mean_logic']:.3f} & "
                    f"{_tex_pct(dfs['consistency_rate'])} & "
                    f"{_tex_pct(dfs['contamination_rate'])} \\\\"
                )
            else:
                lines.append(f"    {_tex_escape(doctrine)} & --- & --- & --- & --- \\\\")

        lines.append(r"    \bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\caption{Mean doctrine fidelity scores by condition.}")
        lines.append(r"\end{table}")

        return "\n".join(lines)

    def _behavioral_consistency(self, data: Dict) -> str:
        bci = data.get("bci")
        if not bci or "summary" not in bci:
            return ""

        lines = [r"\section{Behavioral Consistency Index (BCI)}", ""]
        lines.append(
            "BCI measures action distribution variance across repeated runs. "
            "Low BCI ($\\to 0$) indicates the doctrine reliably channels behavior; "
            "high BCI ($\\to 1$) indicates stochastic behavior despite prescription."
        )
        lines.append("")
        lines.append(r"\begin{table}[h]")
        lines.append(r"\centering")
        lines.append(r"\begin{tabular}{lrrr}")
        lines.append(r"    \toprule")
        lines.append(r"    Condition & BCI (Action) & BCI (Category) & Runs \\")
        lines.append(r"    \midrule")

        for cond, summary in bci["summary"].items():
            ba = summary.get("bci_action")
            bc = summary.get("bci_category")
            lines.append(
                f"    {_tex_escape(cond)} & "
                f"{ba if ba is not None else '---'} & "
                f"{bc if bc is not None else '---'} & "
                f"{summary.get('n_runs', '---')} \\\\"
            )

        lines.append(r"    \bottomrule")
        lines.append(r"\end{tabular}")
        lines.append(r"\caption{Behavioral consistency by doctrine condition.}")
        lines.append(r"\end{table}")

        return "\n".join(lines)

    def _turning_points(self, data: Dict, analyst: Optional[Dict]) -> str:
        inflections = data.get("inflection_decisions", [])
        if not inflections:
            return ""

        lines = [r"\section{Key Turning Points}", ""]

        if analyst and analyst.get("turning_points"):
            lines.append(_tex_escape(analyst["turning_points"]))
        else:
            lines.append(r"\begin{itemize}")
            for dec in inflections:
                lines.append(
                    rf"\item \textbf{{Turn {dec['turn']}}} "
                    rf"({_tex_escape(dec['doctrine'])}, {_tex_escape(dec['provider_name'])}, "
                    rf"{_tex_escape(dec['model_id'])}, {_tex_escape(dec['actor'])}, "
                    rf"{_tex_escape(dec.get('run_label', dec['run_id']))}): "
                    rf"\texttt{{{_tex_escape(dec['action_type'])}}} --- "
                    rf"{_tex_escape(dec['selection_reason'])}"
                )
            lines.append(r"\end{itemize}")

        return "\n".join(lines)

    def _cross_doctrine_findings(self, analyst: Optional[Dict]) -> str:
        if not analyst or not analyst.get("cross_doctrine_findings"):
            return ""
        return (
            r"\section{Cross-Doctrine Findings}" + "\n\n"
            + _tex_escape(analyst["cross_doctrine_findings"])
        )

    def _limitations(self, data: Dict, analyst: Optional[Dict]) -> str:
        lines = [r"\section{Limitations}", ""]

        if analyst and analyst.get("methodology_notes"):
            lines.append(_tex_escape(analyst["methodology_notes"]))
        else:
            meta = data["metadata"]
            lines.append(
                f"This analysis is based on {meta['total_runs']} total runs. "
                "Small sample sizes limit statistical power and the generalizability "
                "of observed patterns. Action distributions may reflect the "
                "available action space constraints as much as doctrine effects. "
                "LLM behavior is sensitive to prompt engineering and model version; "
                "results should be interpreted as indicative rather than definitive."
            )

        return "\n".join(lines)

    def _end_document(self) -> str:
        return r"\end{document}"


# ── Utility ──────────────────────────────────────────────────────────────────

def _tex_pct(value: float) -> str:
    """Format a float as a LaTeX-safe percentage string (e.g., 0.875 -> '87.5\\%')."""
    return f"{value * 100:.1f}\\%"


def _tex_escape(text: str) -> str:
    """Escape special LaTeX characters in user-generated text."""
    if not text:
        return ""
    replacements = [
        ("\\", r"\textbackslash{}"),
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("{", r"\{"),
        ("}", r"\}"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text
