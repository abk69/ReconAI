"""Deterministic validation of structured procurement candidates."""

from __future__ import annotations

from app.domain.enums import DocumentType
from app.extraction.schemas import (
    GoodsReceiptCandidate,
    InvoiceCandidate,
    PurchaseOrderCandidate,
    ValidationIssue,
    ValidationResult,
)


def validate_candidate(
    *,
    document_type: DocumentType,
    candidate: PurchaseOrderCandidate | GoodsReceiptCandidate | InvoiceCandidate | None,
    extraction_warnings: list[str] | None = None,
) -> ValidationResult:
    """Validate a structured candidate. Missing optional fields are not errors."""
    issues: list[ValidationIssue] = []
    requires_review = False
    warnings = extraction_warnings or []

    if any("OCR unavailable" in w or "not installed" in w for w in warnings):
        requires_review = True
        issues.append(
            ValidationIssue(
                code="OCR_UNAVAILABLE",
                message="Image OCR was unavailable; human review required.",
                severity="review",
            )
        )

    if candidate is None or document_type is DocumentType.UNKNOWN:
        requires_review = True
        issues.append(
            ValidationIssue(
                code="UNKNOWN_OR_EMPTY",
                message="Document type is unknown or no structured candidate was produced.",
                severity="review",
            )
        )
        return ValidationResult(is_valid=False, requires_review=True, issues=issues)

    if isinstance(candidate, PurchaseOrderCandidate):
        issues.extend(_validate_po(candidate))
    elif isinstance(candidate, GoodsReceiptCandidate):
        issues.extend(_validate_grn(candidate))
    elif isinstance(candidate, InvoiceCandidate):
        issues.extend(_validate_invoice(candidate))

    hard_errors = [i for i in issues if i.severity == "error"]
    review_issues = [i for i in issues if i.severity == "review"]
    if review_issues:
        requires_review = True

    is_valid = not hard_errors and not requires_review
    if hard_errors and not requires_review:
        # Pure validation failure
        return ValidationResult(is_valid=False, requires_review=False, issues=issues)
    if requires_review:
        return ValidationResult(is_valid=False, requires_review=True, issues=issues)
    return ValidationResult(is_valid=is_valid, requires_review=False, issues=issues)


def _validate_po(candidate: PurchaseOrderCandidate) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not candidate.po_number:
        issues.append(
            ValidationIssue(
                code="MISSING_PO_NUMBER",
                message="Purchase order number is required.",
                field_name="po_number",
            )
        )
    if not candidate.vendor_name:
        issues.append(
            ValidationIssue(
                code="MISSING_VENDOR",
                message="Vendor name is required.",
                field_name="vendor_name",
            )
        )
    if candidate.order_date is None:
        issues.append(
            ValidationIssue(
                code="MISSING_PO_DATE",
                message="Purchase order date is required.",
                field_name="order_date",
            )
        )
    if not candidate.lines:
        issues.append(
            ValidationIssue(
                code="MISSING_LINES",
                message="At least one purchase order line is required.",
                field_name="lines",
            )
        )
    issues.extend(_validate_lines(candidate.lines, require_price=True))
    return issues


def _validate_grn(candidate: GoodsReceiptCandidate) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not candidate.grn_number:
        issues.append(
            ValidationIssue(
                code="MISSING_GRN_NUMBER",
                message="GRN number is required.",
                field_name="grn_number",
            )
        )
    if candidate.receipt_date is None:
        issues.append(
            ValidationIssue(
                code="MISSING_RECEIPT_DATE",
                message="Receipt date is required.",
                field_name="receipt_date",
            )
        )
    if not candidate.lines:
        issues.append(
            ValidationIssue(
                code="MISSING_LINES",
                message="At least one goods receipt line is required.",
                field_name="lines",
            )
        )
    for line in candidate.lines:
        if line.quantity is None:
            issues.append(
                ValidationIssue(
                    code="INVALID_QUANTITY",
                    message="Received quantity is missing or invalid.",
                    field_name="quantity",
                )
            )
        elif line.quantity <= 0:
            issues.append(
                ValidationIssue(
                    code="INVALID_QUANTITY",
                    message="Received quantity must be positive.",
                    field_name="quantity",
                )
            )
    return issues


def _validate_invoice(candidate: InvoiceCandidate) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not candidate.invoice_number:
        issues.append(
            ValidationIssue(
                code="MISSING_INVOICE_NUMBER",
                message="Invoice number is required.",
                field_name="invoice_number",
            )
        )
    if not candidate.vendor_name:
        issues.append(
            ValidationIssue(
                code="MISSING_VENDOR",
                message="Vendor name is required.",
                field_name="vendor_name",
            )
        )
    if candidate.invoice_date is None:
        issues.append(
            ValidationIssue(
                code="MISSING_INVOICE_DATE",
                message="Invoice date is required.",
                field_name="invoice_date",
            )
        )
    if not candidate.lines:
        issues.append(
            ValidationIssue(
                code="MISSING_LINES",
                message="At least one invoice line is required.",
                field_name="lines",
            )
        )
    issues.extend(_validate_lines(candidate.lines, require_price=True))
    return issues


def _validate_lines(lines: list, *, require_price: bool) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for line in lines:
        if line.quantity is None:
            issues.append(
                ValidationIssue(
                    code="INVALID_QUANTITY",
                    message="Line quantity is missing or could not be normalized.",
                    field_name="quantity",
                )
            )
        elif line.quantity <= 0:
            issues.append(
                ValidationIssue(
                    code="INVALID_QUANTITY",
                    message="Line quantity must be positive.",
                    field_name="quantity",
                )
            )
        if require_price:
            if line.unit_price is None:
                issues.append(
                    ValidationIssue(
                        code="INVALID_PRICE",
                        message="Line unit price is missing or could not be normalized.",
                        field_name="unit_price",
                    )
                )
            elif line.unit_price < 0:
                issues.append(
                    ValidationIssue(
                        code="INVALID_PRICE",
                        message="Line unit price cannot be negative.",
                        field_name="unit_price",
                    )
                )
    return issues
