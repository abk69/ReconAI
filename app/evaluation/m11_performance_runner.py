"""Offline performance baseline. Gemini runs only with --live.

    python -m app.evaluation.m11_performance_runner
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from app.evaluation.m11_performance_dataset import DATASET_ID
from app.evaluation.m11_performance_harness import evaluate_dataset
from app.evaluation.m11_performance_stats import (
    PRICING_VERSION,
    estimate_cost,
    monotonic_ms,
    usage_report,
)


def run_live(api_key: str | None = None) -> dict[str, Any]:
    from app.core.config import get_settings
    from app.llm.gemini import GeminiProvider
    from app.llm.prompts import SYSTEM_INSTRUCTION, build_user_content

    key = api_key
    if key is None:
        key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not key:
        return {"status": "LIVE_NOT_RUN", "dataset": DATASET_ID}
    provider = GeminiProvider()
    started = monotonic_ms()
    try:
        response = provider.extract_structured(
            system_instruction=SYSTEM_INSTRUCTION,
            user_content=build_user_content(document_text="Invoice INV-PERF-1 Total 100.00"),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "LIVE_FAILED",
            "dataset": DATASET_ID,
            "mode": "LIVE_LLM_EVALUATION",
            "error_type": type(exc).__name__,
            "duration_ms": round(monotonic_ms() - started, 3),
        }
    usage = response.usage
    return {
        "status": "OK",
        "dataset": DATASET_ID,
        "mode": "LIVE_LLM_EVALUATION",
        "model": response.model,
        "operation": "m6_extraction",
        "duration_ms": round(monotonic_ms() - started, 3),
        "attempt_count": 1,
        "usage": usage_report(usage.input_tokens, usage.output_tokens, usage.total_tokens),
        "cost": estimate_cost(
            usage.input_tokens,
            usage.output_tokens,
            input_price_per_million=None,
            output_price_per_million=None,
            pricing_version=PRICING_VERSION,
        ),
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"Dataset: {report['dataset']}")
    print(f"Mode: {report['mode']}")
    print(
        "protocol: "
        f"warmup={report['protocol']['warmup_runs']} "
        f"measured={report['protocol']['measured_runs']} "
        f"p95={report['protocol']['p95_method']}"
    )
    for name, summary in report["latency"].items():
        print(
            f"{name}: count={summary['count']} min={summary['min']} "
            f"median={summary['median']} p95={summary['p95']} max={summary['max']}"
        )
    stages = report["stage_ms"]
    print(f"grounding_ms: {stages['grounding']}")
    print(f"planner_ms: {stages['planner']}")
    print(f"execution_ms: {stages['execution']}")
    print(f"m6_status: {report['m6_status']}")
    print(f"usage: {report['usage']['extraction']['status']}")
    print(f"cost: {report['cost']['status']} version={report['cost']['pricing_version']}")
    reliability = report["reliability"]
    print(f"invalid_plan_persisted: {reliability['invalid_plan_persisted']}")
    print(f"rollback: {reliability['rollback']['rolled_back']}")
    print(f"duplicate_side_effects: {reliability['duplicate_side_effects']}")
    print(f"idempotency_same_result: {reliability['idempotency']['same_result']}")
    if report["regression_failures"]:
        print("regression_failures:")
        for item in report["regression_failures"]:
            print(f"  {item}")
    else:
        print("regression_failures: none")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M11.5 performance evaluation")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.live:
        result = run_live()
        print(json.dumps(result))
        return 0 if result.get("status") in {"OK", "LIVE_NOT_RUN"} else 1
    report = evaluate_dataset()
    if args.json:
        print(json.dumps(report))
    else:
        _print_report(report)
    return 1 if report["regression_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
