"""
Report graph generation for OSE analysis output.

Graphs are rendered as self-contained SVG files so the report pipeline stays
dependency-light and works without matplotlib.
"""
from __future__ import annotations

from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple


PALETTE = [
    "#0b6e4f",
    "#1d4ed8",
    "#b45309",
    "#7c3aed",
    "#be123c",
    "#0891b2",
    "#4d7c0f",
    "#9f1239",
]


def build_graph_assets(
    report_data: Dict[str, Any],
    output_dir: Path,
    base_name: str,
) -> List[Dict[str, str]]:
    """Generate SVG assets and return lightweight metadata for renderers."""
    asset_dir = output_dir / f"{base_name}_assets"
    asset_dir.mkdir(parents=True, exist_ok=True)

    graphs: List[Dict[str, str]] = []

    config_stats = list(report_data.get("by_configuration", {}).values())
    if config_stats:
        final_tension_path = asset_dir / "final_tension_by_configuration.svg"
        final_tension_path.write_text(
            _render_bar_chart(
                title="Final Tension by Doctrine / Model",
                entries=[
                    {
                        "label": _short_label(stat["model_id"]),
                        "group": stat["doctrine"],
                        "value": float(stat["mean_final_tension"]),
                        "note": stat["outcomes"],
                    }
                    for stat in config_stats
                ],
            ),
            encoding="utf-8",
        )
        graphs.append(
            {
                "kind": "overview",
                "title": "Final Tension by Doctrine / Model",
                "path": str(final_tension_path),
                "relative_path": str(final_tension_path.relative_to(output_dir)),
            }
        )

        latency_path = asset_dir / "latency_by_configuration.svg"
        latency_path.write_text(
            _render_bar_chart(
                title="Average Decision Latency by Doctrine / Model",
                entries=[
                    {
                        "label": _short_label(stat["model_id"]),
                        "group": stat["doctrine"],
                        "value": float((stat.get("operational_metrics", {}) or {}).get("avg_latency_ms") or 0.0) / 1000.0,
                        "note": {"admission": (stat.get("operational_metrics", {}) or {}).get("admission_status", "unknown")},
                    }
                    for stat in config_stats
                    if (stat.get("operational_metrics", {}) or {}).get("avg_latency_ms") is not None
                ],
            ),
            encoding="utf-8",
        )
        graphs.append(
            {
                "kind": "operations",
                "title": "Average Decision Latency by Doctrine / Model",
                "path": str(latency_path),
                "relative_path": str(latency_path.relative_to(output_dir)),
            }
        )

    model_stats = list(report_data.get("by_model", {}).values())
    if model_stats:
        separation_path = asset_dir / "doctrine_separation_by_model.svg"
        separation_path.write_text(
            _render_bar_chart(
                title="Doctrine Separation Score by Model",
                entries=[
                    {
                        "label": _short_label(stat["model_id"]),
                        "group": stat["provider_name"],
                        "value": float((stat.get("doctrine_separation") or {}).get("score") or 0.0),
                        "note": {"doctrines": len(stat.get("doctrines_covered", []))},
                    }
                    for stat in model_stats
                    if stat.get("doctrine_separation") is not None
                ],
            ),
            encoding="utf-8",
        )
        graphs.append(
            {
                "kind": "comparison",
                "title": "Doctrine Separation Score by Model",
                "path": str(separation_path),
                "relative_path": str(separation_path.relative_to(output_dir)),
            }
        )

    by_doctrine: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for stat in config_stats:
        by_doctrine[stat["doctrine"]].append(stat)

    for doctrine, doctrine_stats in sorted(by_doctrine.items()):
        if not doctrine_stats:
            continue
        doctrine_path = asset_dir / f"{_slug(doctrine)}_model_trajectories.svg"
        doctrine_path.write_text(
            _render_line_chart(
                title=f"{doctrine.title()} Doctrine: Tension Trajectories by Model",
                series=[
                    {
                        "label": _short_label(stat["model_id"]),
                        "points": [(turn, mean) for turn, mean, _ in stat["mean_tension_trajectory"]],
                    }
                    for stat in sorted(doctrine_stats, key=lambda item: item["model_id"])
                ],
            ),
            encoding="utf-8",
        )
        graphs.append(
            {
                "kind": "doctrine",
                "doctrine": doctrine,
                "title": f"{doctrine.title()} Doctrine: Tension Trajectories by Model",
                "path": str(doctrine_path),
                "relative_path": str(doctrine_path.relative_to(output_dir)),
            }
        )

    return graphs


def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in value).strip("_")


def _short_label(model_id: str) -> str:
    if "/" in model_id:
        model_id = model_id.split("/", 1)[1]
    return model_id.replace(":free", "_free")


def _render_bar_chart(title: str, entries: Sequence[Dict[str, Any]]) -> str:
    width = 1180
    height = 520
    left = 80
    right = 40
    top = 70
    bottom = 160
    plot_width = width - left - right
    plot_height = height - top - bottom

    if not entries:
        return _empty_svg(width, height, title, "No data available.")

    bar_gap = 18
    bar_width = max(18, int((plot_width - bar_gap * (len(entries) - 1)) / max(len(entries), 1)))
    max_value = max(1.0, max(float(entry["value"]) for entry in entries))

    parts = [_svg_open(width, height, title)]
    parts.append(_chart_title(width / 2, 28, title))
    parts.append(_axis_frame(left, top, plot_width, plot_height))

    for tick in range(6):
        value = tick / 5
        y = top + plot_height - (value / max_value) * plot_height
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" '
            'stroke="#d7dde5" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" '
            'font-size="12" fill="#374151">'
            f"{value:.1f}</text>"
        )

    for idx, entry in enumerate(entries):
        x = left + idx * (bar_width + bar_gap)
        value = float(entry["value"])
        bar_height = (value / max_value) * plot_height
        y = top + plot_height - bar_height
        color = PALETTE[idx % len(PALETTE)]
        group = escape(str(entry.get("group", "")))
        label = escape(str(entry["label"]))
        note = ", ".join(f"{k}:{v}" for k, v in sorted(entry.get("note", {}).items()))
        parts.append(
            f'<rect x="{x}" y="{y:.1f}" width="{bar_width}" height="{bar_height:.1f}" '
            f'fill="{color}" rx="4" ry="4">'
            f"<title>{group} / {label}: {value:.3f} | {escape(note)}</title></rect>"
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{top + plot_height + 22}" text-anchor="end" '
            'transform="rotate(-35 '
            f'{x + bar_width / 2:.1f} {top + plot_height + 22})" font-size="12" fill="#111827">'
            f"{label}</text>"
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{top + plot_height + 44}" text-anchor="end" '
            'transform="rotate(-35 '
            f'{x + bar_width / 2:.1f} {top + plot_height + 44})" font-size="11" fill="#6b7280">'
            f"{group}</text>"
        )
        parts.append(
            f'<text x="{x + bar_width / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" '
            'font-size="12" fill="#111827">'
            f"{value:.2f}</text>"
        )

    parts.append(
        f'<text x="{left + plot_width / 2:.1f}" y="{height - 18}" text-anchor="middle" '
        'font-size="12" fill="#374151">Model configuration</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _render_line_chart(title: str, series: Sequence[Dict[str, Any]]) -> str:
    width = 1180
    height = 480
    left = 80
    right = 220
    top = 70
    bottom = 60
    plot_width = width - left - right
    plot_height = height - top - bottom

    if not series:
        return _empty_svg(width, height, title, "No data available.")

    all_points = [pt for line in series for pt in line["points"]]
    if not all_points:
        return _empty_svg(width, height, title, "No trajectory data available.")

    max_turn = max(point[0] for point in all_points)
    max_turn = max(1, max_turn)

    parts = [_svg_open(width, height, title)]
    parts.append(_chart_title(width / 2, 28, title))
    parts.append(_axis_frame(left, top, plot_width, plot_height))

    for tick in range(6):
        value = tick / 5
        y = top + plot_height - value * plot_height
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_width}" y2="{y:.1f}" '
            'stroke="#d7dde5" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" '
            'font-size="12" fill="#374151">'
            f"{value:.1f}</text>"
        )

    for tick in range(max_turn + 1):
        x = left + (tick / max_turn) * plot_width
        parts.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_height}" '
            'stroke="#eef2f7" stroke-width="1" />'
        )
        parts.append(
            f'<text x="{x:.1f}" y="{top + plot_height + 22}" text-anchor="middle" '
            'font-size="12" fill="#374151">'
            f"{tick}</text>"
        )

    for idx, line in enumerate(series):
        color = PALETTE[idx % len(PALETTE)]
        points = line["points"]
        path_points = []
        for turn, value in points:
            x = left + (turn / max_turn) * plot_width
            y = top + plot_height - max(0.0, min(1.0, float(value))) * plot_height
            path_points.append((x, y))

        if len(path_points) == 1:
            x, y = path_points[0]
            parts.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}">'
                f"<title>{escape(str(line['label']))}</title></circle>"
            )
        else:
            d = " ".join(
                ("M" if i == 0 else "L") + f" {x:.1f} {y:.1f}"
                for i, (x, y) in enumerate(path_points)
            )
            parts.append(
                f'<path d="{d}" fill="none" stroke="{color}" stroke-width="3" '
                'stroke-linecap="round" stroke-linejoin="round" />'
            )
            for x, y in path_points:
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.5" fill="{color}" />')

        legend_y = top + idx * 26
        legend_x = left + plot_width + 28
        parts.append(f'<line x1="{legend_x}" y1="{legend_y}" x2="{legend_x + 24}" y2="{legend_y}" stroke="{color}" stroke-width="3" />')
        parts.append(
            f'<text x="{legend_x + 34}" y="{legend_y + 4}" font-size="12" fill="#111827">'
            f"{escape(str(line['label']))}</text>"
        )

    parts.append(
        f'<text x="{left + plot_width / 2:.1f}" y="{height - 16}" text-anchor="middle" '
        'font-size="12" fill="#374151">Turn</text>'
    )
    parts.append("</svg>")
    return "\n".join(parts)


def _svg_open(width: int, height: int, title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        '<rect width="100%" height="100%" fill="#ffffff" />'
    )


def _chart_title(x: float, y: float, title: str) -> str:
    return (
        f'<text x="{x:.1f}" y="{y}" text-anchor="middle" font-size="20" '
        'font-weight="700" fill="#111827">'
        f"{escape(title)}</text>"
    )


def _axis_frame(left: int, top: int, width: int, height: int) -> str:
    return (
        f'<rect x="{left}" y="{top}" width="{width}" height="{height}" '
        'fill="#f8fafc" stroke="#cbd5e1" stroke-width="1.5" rx="8" ry="8" />'
    )


def _empty_svg(width: int, height: int, title: str, message: str) -> str:
    return "\n".join(
        [
            _svg_open(width, height, title),
            _chart_title(width / 2, 28, title),
            f'<text x="{width / 2:.1f}" y="{height / 2:.1f}" text-anchor="middle" '
            'font-size="16" fill="#6b7280">'
            f"{escape(message)}</text>",
            "</svg>",
        ]
    )
