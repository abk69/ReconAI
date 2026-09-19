"""Compare golden truth vs M4 vs Gemini candidates (small evaluation set).

Usage (offline, no API):
    python -m app.evaluation.m6_runner

Usage (optional live Gemini for REVIEW_REQUIRED fixtures only):
    python -m app.evaluation.m6_runner --live
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from typing import Any

from app.domain.enums import DocumentType
from app.evaluation.evaluator import ExtractionEvaluator
from app.evaluation.golden import GOLDEN_DATASET
from app.evaluation.schemas import EvaluationResult


def _simulate_m4_candidate(golden_expected: dict[str, Any]) -> dict[str, Any]:
    """Deterministic stand-in: copy golden (perfect M4) for offline baseline."""
    return json.loads(json.dumps(golden_expected, default=str))


def _simulate_weak_m4(golden_expected: dict[str, Any]) -> dict[str, Any]:
    """Ambiguous M4: drop identifiers to force review-style gaps."""
    weak = _simulate_m4_candidate(golden_expected)
    for key in ("invoice_number", "po_number", "grn_number", "vendor_name"):
        if key in weak:
            weak[key] = None
    return weak


def run_offline_evaluation() -> dict[str, Any]:
    evaluator = ExtractionEvaluator()
    m4_results: list[EvaluationResult] = []
    gemini_as_m4_proxy: list[EvaluationResult] = []

    for golden in GOLDEN_DATASET:
        if golden.document_type is DocumentType.UNKNOWN:
            continue
        m4_candidate = _simulate_m4_candidate(golden.expected)
        m4_results.append(evaluator.evaluate(golden, m4_candidate))
        # Offline: Gemini proxy uses same golden (measures harness, not live model).
        gemini_as_m4_proxy.append(evaluator.evaluate(golden, m4_candidate))

    def _summary(results: list[EvaluationResult]) -> dict[str, Any]:
        if not results:
            return {
                "documents": 0,
                "field_accuracy_avg": "0",
                "completeness_avg": "0",
                "document_success_rate": 0.0,
                "review_required_rate": 0.0,
            }
        acc = sum((r.field_accuracy for r in results), Decimal("0")) / Decimal(len(results))
        comp = sum((r.completeness for r in results), Decimal("0")) / Decimal(len(results))
        success = sum(1 for r in results if r.overall_success) / len(results)
        review = sum(1 for r in results if not r.overall_success) / len(results)
        return {
            "documents": len(results),
            "field_accuracy_avg": str(acc.quantize(Decimal("0.0001"))),
            "completeness_avg": str(comp.quantize(Decimal("0.0001"))),
            "document_success_rate": success,
            "review_required_rate": review,
        }

    return {
        "m4": _summary(m4_results),
        "gemini_offline_proxy": _summary(gemini_as_m4_proxy),
        "note": (
            "Offline runner uses golden copies as candidates. "
            "Pass --live to evaluate one real Gemini call against clean-invoice."
        ),
    }


def run_live_single() -> dict[str, Any]:
    import os

    from app.core.config import Settings, get_settings
    from app.evaluation.golden import get_golden
    from app.llm.gemini import GeminiProvider
    from app.llm.prompts import SYSTEM_INSTRUCTION, build_user_content
    from app.llm.schemas import gemini_output_to_candidate

    api_key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not api_key:
        return {"error": "GEMINI_API_KEY not configured"}

    golden = get_golden("clean-invoice")
    text = (
        "TAX INVOICE\n"
        "Invoice Number: INV-1001\n"
        "Vendor: Acme Supplies\n"
        "Invoice Date: 2026-09-15\n"
        "PO Number: PO-1001\n"
        "Widget A\n"
        "Quantity: 10\n"
        "Unit Price: 500.00\n"
    )
    provider = GeminiProvider(Settings(gemini_api_key=api_key, llm_model="gemini-3.1-flash-lite"))
    response = provider.extract_structured(
        system_instruction=SYSTEM_INSTRUCTION,
        user_content=build_user_content(document_text=text),
    )
    candidate = gemini_output_to_candidate(response.output)
    m4_candidate = _simulate_weak_m4(golden.expected)
    evaluator = ExtractionEvaluator()
    m4_eval = evaluator.evaluate(golden, m4_candidate)
    gemini_eval = evaluator.evaluate(golden, candidate)
    return {
        "m4": {
            "field_accuracy": str(m4_eval.field_accuracy),
            "completeness": str(m4_eval.completeness),
            "overall_success": m4_eval.overall_success,
        },
        "gemini": {
            "field_accuracy": str(gemini_eval.field_accuracy),
            "completeness": str(gemini_eval.completeness),
            "overall_success": gemini_eval.overall_success,
            "candidate": candidate,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="M6 evaluation runner")
    parser.add_argument("--live", action="store_true", help="Run one live Gemini comparison")
    args = parser.parse_args()
    if args.live:
        print(json.dumps(run_live_single(), indent=2, default=str))
    else:
        print(json.dumps(run_offline_evaluation(), indent=2))


if __name__ == "__main__":
    main()
