"""Unified offline evaluation report. Does not call Gemini.

    python -m app.evaluation.m11_report_runner
    python -m app.evaluation.m11_report_runner --json
    python -m app.evaluation.m11_report_runner --write
"""

from __future__ import annotations

import argparse
from pathlib import Path

from app.evaluation.m11_report import build_report, render_markdown, report_json

WRITE_PATH = Path("evaluation") / "reports" / "m11_unified_report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M11.6 unified evaluation report")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_report()
    if args.json:
        print(report_json(report))
    else:
        print(render_markdown(report))
    if args.write:
        WRITE_PATH.parent.mkdir(parents=True, exist_ok=True)
        WRITE_PATH.write_text(report_json(report), encoding="utf-8")
        print(f"wrote {WRITE_PATH.as_posix()}")
    return 0 if report["evidence_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
