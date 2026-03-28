"""
OSE Report Generator — orchestrates the analysis pipeline.

Usage:
    python -m analysis.report --output reports/
    python -m analysis.report --llm --output reports/
    python -m analysis.report --llm --latex --output reports/

Pipeline:
    1. Discover .db files in --runs directory
    2. AnalysisEngine extracts data + computes statistics
    3. (optional) LLMAnalyst generates qualitative narrative sections
    4. Renderer produces Markdown (always) and LaTeX (if --latex)
    5. Writes output files to --output directory
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from analysis.engine import AnalysisEngine
from analysis.renderer import MarkdownRenderer, LaTeXRenderer


def discover_databases(run_dir: str) -> list[str]:
    """Find all .db files in the given directory."""
    path = Path(run_dir)
    if not path.is_dir():
        print(f"Error: {run_dir} is not a directory.")
        sys.exit(1)

    dbs = sorted(str(p) for p in path.glob("*.db"))
    if not dbs:
        print(f"Error: no .db files found in {run_dir}")
        sys.exit(1)

    return dbs


def _build_report_stem(meta: dict) -> str:
    scenario = meta["scenario"].replace(" ", "_").lower()
    providers = meta.get("providers", [])
    models = meta.get("models", [])
    doctrines = meta.get("conditions", [])

    if len(providers) == 1 and len(models) == 1:
        provider_slug = providers[0].replace("/", "_")
        model_slug = models[0].split("/")[-1].replace(":", "_")
        if len(doctrines) == 1:
            doctrine_slug = doctrines[0].replace(" ", "_").lower()
            return f"{scenario}_{doctrine_slug}_{provider_slug}_{model_slug}"
        return f"{scenario}_{provider_slug}_{model_slug}"

    return f"{scenario}_multi_model"


def generate_report(
    db_paths: list[str],
    use_llm: bool = False,
    use_latex: bool = False,
    output_dir: str = "reports",
) -> dict[str, str]:
    """
    Run the full analysis pipeline and return paths to generated files.

    Returns: {"markdown": path, "latex": path (if --latex), "json": path}
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Step 1: Extract and compute
    print(f"Analyzing {len(db_paths)} run database(s)...")
    engine = AnalysisEngine()
    report_data = engine.analyze(db_paths)

    if "error" in report_data:
        print(f"Error: {report_data['error']}")
        sys.exit(1)

    meta = report_data["metadata"]
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    base_name = f"{_build_report_stem(meta)}_{timestamp}"

    print(f"  Scenario: {meta['scenario']}")
    print(f"  Conditions: {', '.join(meta['conditions'])}")
    print(f"  Providers: {', '.join(meta.get('providers', ['unknown']))}")
    print(f"  Models: {', '.join(meta.get('models', ['unknown']))}")
    print(f"  Total runs: {meta['total_runs']}")

    # Step 2: Optional LLM analysis
    analyst_sections = None
    if use_llm:
        print("Running LLM qualitative analysis...")
        try:
            from analysis.analyst import LLMAnalyst
            analyst = LLMAnalyst()
            analyst_sections = analyst.analyze(report_data)
            if analyst_sections:
                print("  LLM analysis complete.")
            else:
                print("  LLM analysis returned no results — proceeding without.")
        except Exception as e:
            print(f"  LLM analysis failed: {e} — proceeding without.")

    # Step 3: Render Markdown (always)
    print("Rendering Markdown report...")
    md_renderer = MarkdownRenderer()
    md_content = md_renderer.render(report_data, analyst_sections)
    md_path = output_path / f"{base_name}.md"
    md_path.write_text(md_content)
    print(f"  Written: {md_path}")

    result = {"markdown": str(md_path)}

    # Step 4: Render LaTeX (optional)
    if use_latex:
        print("Rendering LaTeX report...")
        tex_renderer = LaTeXRenderer()
        tex_content = tex_renderer.render(report_data, analyst_sections)
        tex_path = output_path / f"{base_name}.tex"
        tex_path.write_text(tex_content)
        print(f"  Written: {tex_path}")
        result["latex"] = str(tex_path)

    # Step 5: Dump raw JSON for programmatic access
    json_path = output_path / f"{base_name}.json"
    # Strip non-serializable data from runs (snapshots can be large)
    slim_data = {
        "metadata": report_data["metadata"],
        "by_doctrine": report_data["by_doctrine"],
        "by_configuration": report_data.get("by_configuration", {}),
        "run_inventory": report_data.get("run_inventory", []),
        "bci": report_data.get("bci"),
        "inflection_decisions": report_data.get("inflection_decisions", []),
        "analyst": analyst_sections,
    }
    json_path.write_text(json.dumps(slim_data, indent=2, default=str))
    print(f"  Written: {json_path}")
    result["json"] = str(json_path)

    return result


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(
        description="Generate an OSE experiment analysis report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m analysis.report\n"
            "  python -m analysis.report --llm --latex\n"
            "  python -m analysis.report --output reports/ --llm\n"
            "  python -m analysis reports\n"
            "  python -m analysis reports --runs logs/runs/"
        ),
    )
    parser.add_argument(
        "--runs", default="logs/runs",
        help="Directory containing run .db files (default: logs/runs/)",
    )
    parser.add_argument(
        "--llm", action="store_true",
        help="Enable LLM qualitative analysis (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--latex", action="store_true",
        help="Also generate LaTeX output",
    )
    parser.add_argument(
        "--output", default="reports",
        help="Output directory for generated reports (default: reports/)",
    )

    args = parser.parse_args(argv)
    db_paths = discover_databases(args.runs)

    print(f"OSE Report Generator")
    print(f"Found {len(db_paths)} database(s) in {args.runs}")
    print()

    result = generate_report(
        db_paths=db_paths,
        use_llm=args.llm,
        use_latex=args.latex,
        output_dir=args.output,
    )

    print()
    print("Done. Generated files:")
    for fmt, path in result.items():
        print(f"  [{fmt}] {path}")


if __name__ == "__main__":
    main()
