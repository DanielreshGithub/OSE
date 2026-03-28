"""
Top-level analysis entrypoint.

Supports:
    python -m analysis
    python -m analysis report
    python -m analysis reports
"""
from __future__ import annotations

import sys
from typing import List

from analysis.report import main as report_main


def _normalize_args(argv: List[str]) -> List[str]:
    if argv and argv[0] in {"report", "reports", "analyze"}:
        return argv[1:]
    return argv


def main(argv: List[str] | None = None) -> None:
    normalized = _normalize_args(list(sys.argv[1:] if argv is None else argv))
    report_main(normalized)


if __name__ == "__main__":
    main()
