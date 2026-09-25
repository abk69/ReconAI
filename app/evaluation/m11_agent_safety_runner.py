"""Offline agent safety evaluation. Gemini runs only with --live.

    python -m app.evaluation.m11_agent_safety_runner
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from app.evaluation.m11_agent_safety_dataset import DATASET_ID
from app.evaluation.m11_agent_safety_harness import evaluate_dataset


def run_live(api_key: str | None = None) -> dict[str, Any]:
    """Bounded planner smoke. It does not approve or execute."""
    from app.core.config import get_settings
    from app.evaluation.m8_harness import run_live_smoke

    key = api_key
    if key is None:
        key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not key:
        return {"status": "LIVE_NOT_RUN", "dataset": DATASET_ID}
    try:
        smoke = run_live_smoke()
    except Exception as exc:  # noqa: BLE001
        return {"status": "LIVE_FAILED", "dataset": DATASET_ID, "error_type": type(exc).__name__}
    status = smoke.get("status")
    if status == "KEY_ABSENT_LIVE_SKIPPED":
        return {"status": "LIVE_NOT_RUN", "dataset": DATASET_ID}
    forbidden = list(smoke.get("forbidden") or [])
    allowlist_ok = smoke.get("allowlist_ok", True)
    if forbidden or allowlist_ok is False:
        return {
            "status": "UNSAFE_PLANNER_OUTPUT",
            "dataset": DATASET_ID,
            "mode": "LIVE_LLM_EVALUATION",
            "executed": 0,
            "forbidden": forbidden,
        }
    return {
        "status": status or "OK",
        "dataset": DATASET_ID,
        "mode": "LIVE_LLM_EVALUATION",
        "executed": 0,
        "allowlist_ok": allowlist_ok,
        "action_types": list(smoke.get("action_types") or []),
    }


def _print_report(report: dict[str, Any]) -> None:
    metrics = report["metrics"]
    print(f"Dataset: {report['dataset']}")
    print(f"Mode: {report['mode']}")
    print(f"cases: {metrics['cases']}")
    print(f"blocked_safely: {metrics['blocked_safely']}/{metrics['cases']}")
    print(f"unexpectedly_executed: {metrics['unexpectedly_executed']}")
    print(f"plan_validity_rate: {metrics['plan_validity_rate']}")
    print(f"allowlist_enforcement: {metrics['allowlist_enforcement']}")
    print(f"parameter_validity: {metrics['parameter_validity']}")
    print(f"grounding_requirement_enforcement: {metrics['grounding_requirement_enforcement']}")
    print(f"approval_bypass_count: {metrics['approval_bypass_count']}")
    print(f"forbidden_execution_count: {metrics['forbidden_execution_count']}")
    print(f"unsafe_execution_count: {metrics['unsafe_execution_count']}")
    print(f"parameter_tampering_count: {metrics['parameter_tampering_count']}")
    print(f"unknown_action_execution_count: {metrics['unknown_action_execution_count']}")
    print(f"invalid_parameter_execution_count: {metrics['invalid_parameter_execution_count']}")
    print(f"prompt_injection_execution_count: {metrics['prompt_injection_execution_count']}")
    print(f"prompt_injection_violation_count: {metrics['prompt_injection_violation_count']}")
    print(f"idempotency_correct: {metrics['idempotency_correct']}")
    print(f"audit_chain_correct: {metrics['audit_chain_correct']}")
    print(f"provider_failure_closed: {metrics['provider_failure_closed']}")
    if report["regression_failures"]:
        print("regression_failures:")
        for item in report["regression_failures"]:
            print(f"  {item}")
    else:
        print("regression_failures: none")
    print("cases:")
    for case in report["cases"]:
        state = "blocked" if case["blocked_safely"] else "UNEXPECTED"
        print(f"  {case['case_id']} {state} executed={case['unexpectedly_executed']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M11.3 agent safety evaluation")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.live:
        result = run_live()
        print(json.dumps(result, indent=2, default=str))
        safe = result.get("status") in {"OK", "LIVE_NOT_RUN", "PLANNER_REJECTED"}
        return 0 if safe and not result.get("executed") else 1
    report = evaluate_dataset()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)
    return 1 if report["regression_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
