"""Deterministic quality gate — decide whether Gemini should be invoked."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.domain.enums import DocumentType, ExtractionOutcome


@dataclass(frozen=True)
class QualityGateDecision:
    """Result of the cost-control gate before calling Gemini."""

    should_invoke: bool
    reasons: list[str] = field(default_factory=list)


def evaluate_quality_gate(
    *,
    outcome: ExtractionOutcome | str,
    detected_type: DocumentType | str,
    validation: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
) -> QualityGateDecision:
    """Return whether Gemini assistance is needed.

    If M4 already produced ``READY_FOR_RECONCILIATION``, do NOT call Gemini.
    """
    outcome_val = (
        outcome if isinstance(outcome, ExtractionOutcome) else ExtractionOutcome(str(outcome))
    )
    type_val = (
        detected_type
        if isinstance(detected_type, DocumentType)
        else DocumentType(str(detected_type))
    )
    validation = validation or {}
    reasons: list[str] = []

    if outcome_val is ExtractionOutcome.READY_FOR_RECONCILIATION:
        return QualityGateDecision(
            should_invoke=False,
            reasons=["M4 outcome is READY_FOR_RECONCILIATION; Gemini skipped for cost control."],
        )

    if outcome_val is ExtractionOutcome.REVIEW_REQUIRED:
        reasons.append("M4 outcome is REVIEW_REQUIRED.")
    if outcome_val is ExtractionOutcome.VALIDATION_FAILED:
        reasons.append("M4 outcome is VALIDATION_FAILED.")
    if outcome_val is ExtractionOutcome.EXTRACTION_FAILED:
        reasons.append("M4 outcome is EXTRACTION_FAILED.")

    if type_val is DocumentType.UNKNOWN:
        reasons.append("Document type is UNKNOWN.")

    if validation.get("requires_review"):
        reasons.append("M4 validation requires_review=true.")

    for issue in validation.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        code = issue.get("code") or ""
        if code in {
            "OCR_UNAVAILABLE",
            "UNKNOWN_OR_EMPTY",
            "MISSING_INVOICE_NUMBER",
            "MISSING_PO_NUMBER",
            "MISSING_GRN_NUMBER",
            "MISSING_VENDOR",
            "MISSING_LINES",
            "INVALID_QUANTITY",
            "INVALID_PRICE",
        }:
            reasons.append(f"M4 issue: {code}.")

    if candidate is None:
        reasons.append("M4 candidate is empty.")
    elif isinstance(candidate, dict):
        lines = candidate.get("lines")
        if isinstance(lines, list) and len(lines) == 0:
            reasons.append("M4 candidate has no line items.")

    # Deduplicate while preserving order.
    unique: list[str] = []
    seen: set[str] = set()
    for reason in reasons:
        if reason not in seen:
            unique.append(reason)
            seen.add(reason)

    if not unique:
        # Non-ready outcomes without explicit reasons still need assistance.
        unique.append(f"M4 outcome {outcome_val.value} is not ready; invoking Gemini.")

    return QualityGateDecision(should_invoke=True, reasons=unique)
