"""Run M4 on the synthetic dataset. Offline mode does not call Gemini."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.domain.enums import DocumentType
from app.evaluation.m11_dataset import DATASET
from app.evaluation.m11_metrics import evaluate_prediction
from app.evaluation.m11_schema import DATASET_ID, CaseResult, EvalCase
from app.extraction.classifier import classify_document
from app.extraction.schemas import ExtractedDocument, ExtractedTable
from app.extraction.structure import build_candidate

_DOC_ID = UUID("00000000-0000-4000-8000-000000000011")

# Engineering regression gates for this dataset version.
# They freeze the offline M4 measurement. They are not a production accuracy claim.
REGRESSION_GATES = {
    "header_accuracy": "1.0000",
    "header_completeness": "0.7733",
    "line_accuracy": "0.9667",
    "line_completeness": "0.6170",
    "exact_match_rate": "0.6000",
}


def predict_m4(case: EvalCase) -> tuple[dict[str, Any] | None, str]:
    extracted = ExtractedDocument(
        document_id=_DOC_ID,
        pages=[case.source_text],
        full_text=case.source_text,
        tables=[
            ExtractedTable(sheet=table.sheet, headers=table.headers, rows=table.rows)
            for table in case.tables
        ],
        extractor_name="m11-source",
        metadata={"filename": case.filename},
    )
    detected = classify_document(
        extracted,
        declared_type=DocumentType.UNKNOWN,
        original_filename=case.filename,
    )
    candidate, _evidence = build_candidate(extracted, detected)
    if candidate is None:
        return None, detected.value
    payload = candidate.model_dump(mode="json")
    payload.pop("evidence", None)
    for line in payload.get("lines") or []:
        if isinstance(line, dict):
            line.pop("evidence", None)
    return payload, detected.value


def evaluate_case(
    case: EvalCase,
    prediction: dict[str, Any] | None,
    detected_type: str | None,
) -> CaseResult:
    return evaluate_prediction(case, prediction, detected_type)


def run_m4_cases() -> list[CaseResult]:
    results: list[CaseResult] = []
    for case in DATASET:
        prediction, detected = predict_m4(case)
        results.append(evaluate_case(case, prediction, detected))
    return results


def aggregate(results: list[CaseResult]) -> dict[str, Any]:
    documents = len(results)
    header_correct = sum(item.metrics.header_correct for item in results)
    header_comparable = sum(item.metrics.header_accuracy_denominator for item in results)
    header_expected = sum(item.metrics.header_completeness_denominator for item in results)
    line_correct = sum(item.metrics.line_fields_correct for item in results)
    line_comparable = sum(item.metrics.line_accuracy_denominator for item in results)
    line_expected = sum(item.metrics.line_completeness_denominator for item in results)
    exact = sum(1 for item in results if item.metrics.exact_match)
    success = sum(1 for item in results if item.metrics.success)

    def rate(numerator: int, denominator: int) -> str:
        if denominator <= 0:
            return "0.0000"
        from decimal import Decimal

        return str((Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001")))

    return {
        "documents": documents,
        "exact_match_count": exact,
        "exact_match_rate": rate(exact, documents),
        "exact_match_denominator": documents,
        "document_success_count": success,
        "document_success_rate": rate(success, documents),
        "document_success_denominator": documents,
        "header_accuracy": rate(header_correct, header_comparable),
        "header_accuracy_numerator": header_correct,
        "header_accuracy_denominator": header_comparable,
        "header_completeness": rate(header_correct, header_expected),
        "header_completeness_numerator": header_correct,
        "header_completeness_denominator": header_expected,
        "line_accuracy": rate(line_correct, line_comparable),
        "line_accuracy_numerator": line_correct,
        "line_accuracy_denominator": line_comparable,
        "line_completeness": rate(line_correct, line_expected),
        "line_completeness_numerator": line_correct,
        "line_completeness_denominator": line_expected,
    }


def error_breakdown(results: list[CaseResult]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in results:
        for error in result.errors:
            counts[error.category.value] = counts.get(error.category.value, 0) + 1
    return dict(sorted(counts.items()))


def compare_modes(m4: dict[str, Any], m6: dict[str, Any] | None) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    keys = (
        "header_accuracy",
        "header_completeness",
        "line_accuracy",
        "line_completeness",
        "exact_match_rate",
        "document_success_rate",
    )
    for key in keys:
        m4_value = str(m4[key])
        m6_value = None if m6 is None else str(m6.get(key))
        delta = None
        if m6 is not None and m6_value is not None:
            from decimal import Decimal

            delta = str(Decimal(m6_value) - Decimal(m4_value))
        rows.append({"metric": key, "m4": m4_value, "m6": m6_value, "delta": delta})
    return rows


def regression_failures(summary: dict[str, Any]) -> list[str]:
    from decimal import Decimal

    failures: list[str] = []
    for metric, minimum in REGRESSION_GATES.items():
        actual = Decimal(str(summary[metric]))
        if actual < Decimal(minimum):
            failures.append(f"{metric} {actual} < gate {minimum}")
    return failures


def offline_report() -> dict[str, Any]:
    results = run_m4_cases()
    summary = aggregate(results)
    return {
        "dataset": DATASET_ID,
        "mode": "OFFLINE_DETERMINISTIC_EVALUATION",
        "summary": summary,
        "error_breakdown": error_breakdown(results),
        "cases": [result.model_dump(mode="json") for result in results],
        "comparison": compare_modes(summary, None),
        "m6_status": "NOT_RUN",
        "regression_failures": regression_failures(summary),
    }
