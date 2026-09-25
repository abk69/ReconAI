"""Offline extraction evaluation. Gemini runs only with --live.

    python -m app.evaluation.m11_runner
    python -m app.evaluation.m11_runner --live
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from app.evaluation.m11_dataset import DATASET
from app.evaluation.m11_harness import aggregate, evaluate_case, offline_report, predict_m4
from app.evaluation.m11_schema import DATASET_ID


def _print_report(report: dict[str, Any]) -> None:
    summary = report["summary"]
    def ratio_line(label: str, numerator: str, denominator: str, rate: str) -> None:
        print(f"{label}: {summary[numerator]}/{summary[denominator]} = {summary[rate]}")

    print(f"Dataset: {report['dataset']}")
    print(f"Mode: {report['mode']}")
    print(f"documents_evaluated: {summary['documents']}")
    ratio_line(
        "exact_match_rate",
        "exact_match_count",
        "exact_match_denominator",
        "exact_match_rate",
    )
    ratio_line(
        "header_accuracy",
        "header_accuracy_numerator",
        "header_accuracy_denominator",
        "header_accuracy",
    )
    ratio_line(
        "header_completeness",
        "header_completeness_numerator",
        "header_completeness_denominator",
        "header_completeness",
    )
    ratio_line(
        "line_accuracy",
        "line_accuracy_numerator",
        "line_accuracy_denominator",
        "line_accuracy",
    )
    ratio_line(
        "line_completeness",
        "line_completeness_numerator",
        "line_completeness_denominator",
        "line_completeness",
    )
    ratio_line(
        "document_success_rate",
        "document_success_count",
        "document_success_denominator",
        "document_success_rate",
    )
    print("error_breakdown:")
    for name, count in report["error_breakdown"].items():
        print(f"  {name}: {count}")
    print("comparison:")
    for row in report["comparison"]:
        print(f"  {row['metric']}: M4={row['m4']} M6={row['m6']} delta={row['delta']}")
    print(f"m6_status: {report['m6_status']}")
    if report["regression_failures"]:
        print("regression_failures:")
        for item in report["regression_failures"]:
            print(f"  {item}")
    else:
        print("regression_failures: none")
    print("cases:")
    for case in report["cases"]:
        state = "passed" if case["passed"] else "failed"
        print(f"  {case['case_id']} {case['document_type']} {state} errors={len(case['errors'])}")


def run_live() -> dict[str, Any]:
    from app.core.config import Settings, get_settings
    from app.llm.gemini import GeminiProvider
    from app.llm.prompts import SYSTEM_INSTRUCTION, build_user_content
    from app.llm.schemas import gemini_output_to_candidate

    api_key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not api_key:
        return {"status": "KEY_ABSENT_LIVE_SKIPPED", "dataset": DATASET_ID}
    case = next(item for item in DATASET if item.case_id == "clean-invoice")
    settings = get_settings()
    model = settings.llm_model
    provider = GeminiProvider(Settings(gemini_api_key=api_key, llm_model=model))
    try:
        response = provider.extract_structured(
            system_instruction=SYSTEM_INSTRUCTION,
            user_content=build_user_content(document_text=case.source_text),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "LIVE_FAILED",
            "dataset": DATASET_ID,
            "model": model,
            "error_type": type(exc).__name__,
        }
    candidate = gemini_output_to_candidate(response.output)
    m4_prediction, m4_type = predict_m4(case)
    m4_result = evaluate_case(case, m4_prediction, m4_type)
    m6_result = evaluate_case(case, candidate, str(response.output.document_type))
    m4_summary = aggregate([m4_result])
    m6_summary = aggregate([m6_result])
    return {
        "status": "OK",
        "dataset": DATASET_ID,
        "mode": "LIVE_LLM_EVALUATION",
        "model": model,
        "case_id": case.case_id,
        "m4": m4_summary,
        "m6": m6_summary,
        "m6_error_count": len(m6_result.errors),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M11 extraction evaluation")
    parser.add_argument("--live", action="store_true", help="Score one case with Gemini")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    args = parser.parse_args(argv)
    if args.live:
        result = run_live()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") in {"OK", "KEY_ABSENT_LIVE_SKIPPED"} else 1
    report = offline_report()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)
    return 1 if report["regression_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
