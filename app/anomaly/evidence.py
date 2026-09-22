"""Structured evidence helpers and deterministic explanations (no LLM)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any


def decimal_str(value: Decimal) -> str:
    """Canonical decimal string for evidence (never float)."""
    return format(value, "f")


def severity_from_percent_thresholds(
    variance_pct: Decimal,
    *,
    low: Decimal,
    medium: Decimal,
    high: Decimal,
    critical: Decimal,
) -> str | None:
    """Return severity name for the highest met percent threshold, or None."""
    if variance_pct < low:
        return None
    if variance_pct >= critical:
        return "CRITICAL"
    if variance_pct >= high:
        return "HIGH"
    if variance_pct >= medium:
        return "MEDIUM"
    return "LOW"


def severity_from_ratio_thresholds(
    ratio: Decimal,
    *,
    medium: Decimal,
    high: Decimal,
    critical: Decimal,
) -> str | None:
    """Vendor-spike style: ratio must meet at least medium to signal."""
    if ratio < medium:
        return None
    if ratio >= critical:
        return "CRITICAL"
    if ratio >= high:
        return "HIGH"
    return "MEDIUM"


def severity_from_rate_thresholds(
    rate: Decimal,
    *,
    medium: Decimal,
    high: Decimal,
    critical: Decimal,
) -> str | None:
    """Repeated-mismatch style: rate must meet at least medium to signal."""
    if rate < medium:
        return None
    if rate >= critical:
        return "CRITICAL"
    if rate >= high:
        return "HIGH"
    return "MEDIUM"


def explain_from_evidence(anomaly_type: str, evidence: dict[str, Any]) -> tuple[str, str]:
    """Build (title, explanation) deterministically from structured evidence."""
    if anomaly_type == "PRICE_VARIANCE":
        title = "Invoice unit price variance vs purchase order"
        explanation = (
            f"Invoice unit price {evidence.get('invoice_unit_price')} differs from "
            f"PO unit price {evidence.get('po_unit_price')} "
            f"({evidence.get('variance_percent')}% variance)."
        )
        return title, explanation
    if anomaly_type == "QUANTITY_VARIANCE":
        title = "Invoice quantity variance vs expected quantity"
        explanation = (
            f"Invoiced quantity {evidence.get('invoiced_quantity')} differs from "
            f"expected quantity {evidence.get('expected_quantity')} "
            f"({evidence.get('variance_percent')}% variance)."
        )
        return title, explanation
    if anomaly_type == "DUPLICATE_INVOICE":
        title = "Possible duplicate invoice identity"
        explanation = (
            f"Vendor has {evidence.get('duplicate_count')} invoice records sharing "
            f"normalized invoice number {evidence.get('normalized_invoice_number')}."
        )
        return title, explanation
    if anomaly_type == "TIMING_ANOMALY":
        kind = evidence.get("timing_kind", "timing")
        if kind == "invoice_before_po":
            title = "Invoice date precedes purchase order date"
            explanation = "Invoice date precedes purchase order date."
        elif kind == "invoice_before_grn":
            title = "Invoice date precedes goods receipt date"
            explanation = "Invoice date precedes goods receipt (GRN) date."
        else:
            title = "Unusually long PO-to-invoice delay"
            explanation = (
                f"Invoice date is {evidence.get('delay_days')} days after the "
                f"purchase order date (threshold {evidence.get('threshold_days')} days)."
            )
        return title, explanation
    if anomaly_type == "VENDOR_SPIKE":
        title = "Invoice value above vendor historical baseline"
        explanation = (
            f"Invoice value {evidence.get('current_value')} is "
            f"{evidence.get('ratio')}x the vendor's recent baseline average "
            f"{evidence.get('baseline_average')} "
            f"(n={evidence.get('historical_invoice_count')})."
        )
        return title, explanation
    if anomaly_type == "REPEATED_MISMATCH":
        title = "Elevated vendor reconciliation exception rate"
        explanation = (
            f"Vendor has {evidence.get('exception_count')} reconciliation exceptions "
            f"across {evidence.get('invoice_count')} invoices "
            f"({evidence.get('exception_rate')} rate) in a "
            f"{evidence.get('window_days')}-day window."
        )
        return title, explanation
    title = "Procurement anomaly signal"
    explanation = "Deterministic anomaly signal detected."
    return title, explanation
