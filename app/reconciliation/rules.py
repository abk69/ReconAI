"""Pure deterministic reconciliation rule helpers.

All arithmetic uses ``Decimal``. No FastAPI / ORM / AI dependencies.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from uuid import UUID

from app.domain.enums import ExceptionSeverity, ExceptionType
from app.reconciliation.schemas import (
    EngineGoodsReceipt,
    EngineInvoice,
    EngineInvoiceLine,
    EnginePurchaseOrder,
    EnginePurchaseOrderLine,
    ExceptionDraft,
    ReconciliationConfig,
)


def normalize_invoice_number(value: str) -> str:
    """Conservative invoice-number normalization for duplicate detection."""
    normalized = value.strip().casefold()
    normalized = re.sub(r"[\s_]+", "-", normalized)
    normalized = re.sub(r"-{2,}", "-", normalized)
    return normalized.strip("-")


def _decimal_str(value: Decimal) -> str:
    return format(value, "f")


def build_fingerprint(*parts: object) -> str:
    """Stable SHA-256 fingerprint from ordered identity parts."""
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def percent_variance(expected: Decimal, actual: Decimal) -> Decimal:
    """Return percentage variance of ``actual`` vs ``expected``."""
    if expected == 0:
        return Decimal("0") if actual == 0 else Decimal("100")
    return (abs(actual - expected) / abs(expected)) * Decimal("100")


def exceeds_percent_tolerance(
    expected: Decimal,
    actual: Decimal,
    tolerance_percent: Decimal,
) -> bool:
    return percent_variance(expected, actual) > tolerance_percent


def exceeds_quantity_tolerance(
    left: Decimal,
    right: Decimal,
    tolerance: Decimal,
) -> bool:
    """True when ``left`` is greater than ``right`` beyond absolute tolerance."""
    return left > right + tolerance


def match_line_to_po(
    *,
    purchase_order: EnginePurchaseOrder,
    purchase_order_line_id: UUID | None,
    line_number: int,
    document_label: str,
    document_id: UUID,
    line_id: UUID,
) -> tuple[EnginePurchaseOrderLine | None, ExceptionDraft | None]:
    """Resolve a GRN/invoice line to a PO line using FKs, then unambiguous line_number."""
    po_lines_by_id = {line.id: line for line in purchase_order.lines}
    po_lines_by_number: dict[int, list[EnginePurchaseOrderLine]] = {}
    for line in purchase_order.lines:
        po_lines_by_number.setdefault(line.line_number, []).append(line)

    if purchase_order_line_id is not None:
        matched = po_lines_by_id.get(purchase_order_line_id)
        if matched is None:
            draft = ExceptionDraft(
                exception_type=ExceptionType.IDENTIFIER_MISMATCH,
                severity=ExceptionSeverity.HIGH,
                message=(
                    f"{document_label} line references purchase order line "
                    f"{purchase_order_line_id} which does not exist on PO "
                    f"{purchase_order.po_number}."
                ),
                fingerprint=build_fingerprint(
                    ExceptionType.IDENTIFIER_MISMATCH.value,
                    "missing_po_line_ref",
                    document_id,
                    line_id,
                    purchase_order_line_id,
                ),
                purchase_order_id=purchase_order.id,
                goods_receipt_id=document_id if document_label == "GRN" else None,
                invoice_id=document_id if document_label == "Invoice" else None,
                source_document_ids=[purchase_order.id, document_id],
                evidence={
                    "document_type": document_label,
                    "document_id": str(document_id),
                    "line_id": str(line_id),
                    "referenced_purchase_order_line_id": str(purchase_order_line_id),
                    "purchase_order_id": str(purchase_order.id),
                },
            )
            return None, draft
        return matched, None

    candidates = po_lines_by_number.get(line_number, [])
    if len(candidates) == 1:
        return candidates[0], None

    draft = ExceptionDraft(
        exception_type=ExceptionType.IDENTIFIER_MISMATCH,
        severity=ExceptionSeverity.HIGH,
        message=(
            f"{document_label} line {line_number} cannot be matched confidently "
            f"to a purchase order line on PO {purchase_order.po_number}."
        ),
        fingerprint=build_fingerprint(
            ExceptionType.IDENTIFIER_MISMATCH.value,
            "ambiguous_or_missing_line",
            document_id,
            line_id,
            line_number,
        ),
        purchase_order_id=purchase_order.id,
        goods_receipt_id=document_id if document_label == "GRN" else None,
        invoice_id=document_id if document_label == "Invoice" else None,
        source_document_ids=[purchase_order.id, document_id],
        evidence={
            "document_type": document_label,
            "document_id": str(document_id),
            "line_id": str(line_id),
            "line_number": line_number,
            "candidate_count": len(candidates),
            "purchase_order_id": str(purchase_order.id),
        },
    )
    return None, draft


def check_header_po_reference(
    *,
    purchase_order: EnginePurchaseOrder,
    referenced_po_id: UUID | None,
    document_label: str,
    document_id: UUID,
) -> ExceptionDraft | None:
    if referenced_po_id is None:
        return ExceptionDraft(
            exception_type=ExceptionType.IDENTIFIER_MISMATCH,
            severity=ExceptionSeverity.HIGH,
            message=f"{document_label} does not reference a purchase order.",
            fingerprint=build_fingerprint(
                ExceptionType.IDENTIFIER_MISMATCH.value,
                "missing_po_header_ref",
                document_id,
                purchase_order.id,
            ),
            purchase_order_id=purchase_order.id,
            goods_receipt_id=document_id if document_label == "GRN" else None,
            invoice_id=document_id if document_label == "Invoice" else None,
            source_document_ids=[purchase_order.id, document_id],
            evidence={
                "document_type": document_label,
                "document_id": str(document_id),
                "expected_purchase_order_id": str(purchase_order.id),
                "actual_purchase_order_id": None,
            },
        )
    if referenced_po_id != purchase_order.id:
        return ExceptionDraft(
            exception_type=ExceptionType.IDENTIFIER_MISMATCH,
            severity=ExceptionSeverity.HIGH,
            message=(
                f"{document_label} references PO {referenced_po_id} but "
                f"reconciliation was run against PO {purchase_order.id}."
            ),
            fingerprint=build_fingerprint(
                ExceptionType.IDENTIFIER_MISMATCH.value,
                "po_header_mismatch",
                document_id,
                referenced_po_id,
                purchase_order.id,
            ),
            purchase_order_id=purchase_order.id,
            goods_receipt_id=document_id if document_label == "GRN" else None,
            invoice_id=document_id if document_label == "Invoice" else None,
            source_document_ids=[purchase_order.id, document_id],
            evidence={
                "document_type": document_label,
                "document_id": str(document_id),
                "expected_purchase_order_id": str(purchase_order.id),
                "actual_purchase_order_id": str(referenced_po_id),
            },
        )
    return None


def quantity_exceptions_for_line(
    *,
    purchase_order: EnginePurchaseOrder,
    po_line: EnginePurchaseOrderLine,
    received_quantity: Decimal,
    invoiced_quantity: Decimal,
    grn_line_ids: list[UUID],
    invoice_line_ids: list[UUID],
    invoice_id: UUID | None,
    goods_receipt_ids: list[UUID],
    config: ReconciliationConfig,
) -> list[ExceptionDraft]:
    """Flag quantity rule violations; do not flag valid partial delivery."""
    drafts: list[ExceptionDraft] = []
    ordered = po_line.quantity
    tolerance = config.quantity_tolerance

    checks: list[tuple[str, Decimal, Decimal, str]] = [
        (
            "invoiced_gt_received",
            invoiced_quantity,
            received_quantity,
            (
                f"Invoiced quantity {_decimal_str(invoiced_quantity)} exceeds received "
                f"quantity {_decimal_str(received_quantity)} on PO line {po_line.line_number}."
            ),
        ),
        (
            "received_gt_ordered",
            received_quantity,
            ordered,
            (
                f"Received quantity {_decimal_str(received_quantity)} exceeds ordered "
                f"quantity {_decimal_str(ordered)} on PO line {po_line.line_number}."
            ),
        ),
        (
            "invoiced_gt_ordered",
            invoiced_quantity,
            ordered,
            (
                f"Invoiced quantity {_decimal_str(invoiced_quantity)} exceeds ordered "
                f"quantity {_decimal_str(ordered)} on PO line {po_line.line_number}."
            ),
        ),
    ]

    for rule_key, left, right, message in checks:
        if not exceeds_quantity_tolerance(left, right, tolerance):
            continue
        drafts.append(
            ExceptionDraft(
                exception_type=ExceptionType.QUANTITY_MISMATCH,
                severity=ExceptionSeverity.HIGH,
                message=message,
                fingerprint=build_fingerprint(
                    ExceptionType.QUANTITY_MISMATCH.value,
                    rule_key,
                    purchase_order.id,
                    po_line.id,
                    invoice_id,
                ),
                purchase_order_id=purchase_order.id,
                goods_receipt_id=goods_receipt_ids[0] if len(goods_receipt_ids) == 1 else None,
                invoice_id=invoice_id,
                source_document_ids=[
                    purchase_order.id,
                    *goods_receipt_ids,
                    *([invoice_id] if invoice_id else []),
                ],
                evidence={
                    "rule": rule_key,
                    "purchase_order_id": str(purchase_order.id),
                    "purchase_order_line_id": str(po_line.id),
                    "line_number": po_line.line_number,
                    "ordered_quantity": _decimal_str(ordered),
                    "received_quantity": _decimal_str(received_quantity),
                    "invoiced_quantity": _decimal_str(invoiced_quantity),
                    "quantity_tolerance": _decimal_str(tolerance),
                    "expected_value": _decimal_str(right),
                    "actual_value": _decimal_str(left),
                    "variance": _decimal_str(left - right),
                    "grn_line_ids": [str(i) for i in grn_line_ids],
                    "invoice_line_ids": [str(i) for i in invoice_line_ids],
                    "goods_receipt_ids": [str(i) for i in goods_receipt_ids],
                },
            )
        )
    return drafts


def price_exception_for_line(
    *,
    purchase_order: EnginePurchaseOrder,
    po_line: EnginePurchaseOrderLine,
    invoice: EngineInvoice,
    invoice_line: EngineInvoiceLine,
    config: ReconciliationConfig,
) -> ExceptionDraft | None:
    expected = po_line.unit_price
    billed = invoice_line.unit_price
    if not exceeds_percent_tolerance(expected, billed, config.price_tolerance_percent):
        return None
    abs_var = abs(billed - expected)
    pct_var = percent_variance(expected, billed)
    return ExceptionDraft(
        exception_type=ExceptionType.PRICE_MISMATCH,
        severity=ExceptionSeverity.HIGH,
        message=(
            f"Unit price mismatch on PO line {po_line.line_number}: "
            f"expected {_decimal_str(expected)}, billed {_decimal_str(billed)}."
        ),
        fingerprint=build_fingerprint(
            ExceptionType.PRICE_MISMATCH.value,
            purchase_order.id,
            po_line.id,
            invoice.id,
            invoice_line.id,
        ),
        purchase_order_id=purchase_order.id,
        invoice_id=invoice.id,
        source_document_ids=[purchase_order.id, invoice.id],
        evidence={
            "purchase_order_id": str(purchase_order.id),
            "purchase_order_line_id": str(po_line.id),
            "invoice_id": str(invoice.id),
            "invoice_line_id": str(invoice_line.id),
            "line_number": po_line.line_number,
            "expected_unit_price": _decimal_str(expected),
            "billed_unit_price": _decimal_str(billed),
            "absolute_variance": _decimal_str(abs_var),
            "percentage_variance": _decimal_str(pct_var),
            "price_tolerance_percent": _decimal_str(config.price_tolerance_percent),
            "expected_value": _decimal_str(expected),
            "actual_value": _decimal_str(billed),
        },
    )


def tax_exception_for_line(
    *,
    purchase_order: EnginePurchaseOrder,
    po_line: EnginePurchaseOrderLine,
    invoice: EngineInvoice,
    invoice_line: EngineInvoiceLine,
    config: ReconciliationConfig,
) -> ExceptionDraft | None:
    expected = po_line.tax_rate
    actual = invoice_line.tax_rate
    if not exceeds_percent_tolerance(expected, actual, config.tax_rate_tolerance_percent):
        return None
    abs_var = abs(actual - expected)
    pct_var = percent_variance(expected, actual)
    return ExceptionDraft(
        exception_type=ExceptionType.TAX_MISMATCH,
        severity=ExceptionSeverity.MEDIUM,
        message=(
            f"Tax rate mismatch on PO line {po_line.line_number}: "
            f"expected {_decimal_str(expected)}, invoiced {_decimal_str(actual)}."
        ),
        fingerprint=build_fingerprint(
            ExceptionType.TAX_MISMATCH.value,
            purchase_order.id,
            po_line.id,
            invoice.id,
            invoice_line.id,
        ),
        purchase_order_id=purchase_order.id,
        invoice_id=invoice.id,
        source_document_ids=[purchase_order.id, invoice.id],
        evidence={
            "purchase_order_id": str(purchase_order.id),
            "purchase_order_line_id": str(po_line.id),
            "invoice_id": str(invoice.id),
            "invoice_line_id": str(invoice_line.id),
            "line_number": po_line.line_number,
            "expected_tax_rate": _decimal_str(expected),
            "actual_tax_rate": _decimal_str(actual),
            "absolute_variance": _decimal_str(abs_var),
            "percentage_variance": _decimal_str(pct_var),
            "tax_rate_tolerance_percent": _decimal_str(config.tax_rate_tolerance_percent),
            "expected_value": _decimal_str(expected),
            "actual_value": _decimal_str(actual),
        },
    )


def date_exceptions(
    *,
    purchase_order: EnginePurchaseOrder,
    goods_receipts: list[EngineGoodsReceipt],
    invoice: EngineInvoice | None,
) -> list[ExceptionDraft]:
    drafts: list[ExceptionDraft] = []
    for grn in goods_receipts:
        if grn.receipt_date < purchase_order.order_date:
            drafts.append(
                ExceptionDraft(
                    exception_type=ExceptionType.DATE_MISMATCH,
                    severity=ExceptionSeverity.MEDIUM,
                    message=(
                        f"GRN {grn.grn_number} date {grn.receipt_date.isoformat()} "
                        f"is before PO {purchase_order.po_number} date "
                        f"{purchase_order.order_date.isoformat()}."
                    ),
                    fingerprint=build_fingerprint(
                        ExceptionType.DATE_MISMATCH.value,
                        "grn_before_po",
                        purchase_order.id,
                        grn.id,
                    ),
                    purchase_order_id=purchase_order.id,
                    goods_receipt_id=grn.id,
                    source_document_ids=[purchase_order.id, grn.id],
                    evidence={
                        "purchase_order_id": str(purchase_order.id),
                        "goods_receipt_id": str(grn.id),
                        "expected_value": purchase_order.order_date.isoformat(),
                        "actual_value": grn.receipt_date.isoformat(),
                        "rule": "grn_date_before_po_date",
                    },
                )
            )
    if invoice is not None and invoice.invoice_date < purchase_order.order_date:
        drafts.append(
            ExceptionDraft(
                exception_type=ExceptionType.DATE_MISMATCH,
                severity=ExceptionSeverity.MEDIUM,
                message=(
                    f"Invoice {invoice.invoice_number} date "
                    f"{invoice.invoice_date.isoformat()} is before PO "
                    f"{purchase_order.po_number} date "
                    f"{purchase_order.order_date.isoformat()}."
                ),
                fingerprint=build_fingerprint(
                    ExceptionType.DATE_MISMATCH.value,
                    "invoice_before_po",
                    purchase_order.id,
                    invoice.id,
                ),
                purchase_order_id=purchase_order.id,
                invoice_id=invoice.id,
                source_document_ids=[purchase_order.id, invoice.id],
                evidence={
                    "purchase_order_id": str(purchase_order.id),
                    "invoice_id": str(invoice.id),
                    "expected_value": purchase_order.order_date.isoformat(),
                    "actual_value": invoice.invoice_date.isoformat(),
                    "rule": "invoice_date_before_po_date",
                },
            )
        )
    return drafts


def missing_document_exception(
    *,
    missing: str,
    purchase_order_id: UUID | None,
    invoice_id: UUID | None,
    goods_receipt_ids: list[UUID],
    source_document_ids: list[UUID],
) -> ExceptionDraft:
    return ExceptionDraft(
        exception_type=ExceptionType.MISSING_DOCUMENT,
        severity=ExceptionSeverity.CRITICAL,
        message=f"Required document missing: {missing}.",
        fingerprint=build_fingerprint(
            ExceptionType.MISSING_DOCUMENT.value,
            missing,
            purchase_order_id,
            invoice_id,
            *sorted(str(i) for i in goods_receipt_ids),
        ),
        purchase_order_id=purchase_order_id,
        invoice_id=invoice_id,
        goods_receipt_id=goods_receipt_ids[0] if len(goods_receipt_ids) == 1 else None,
        source_document_ids=source_document_ids,
        evidence={
            "missing_document": missing,
            "purchase_order_id": str(purchase_order_id) if purchase_order_id else None,
            "invoice_id": str(invoice_id) if invoice_id else None,
            "goods_receipt_ids": [str(i) for i in goods_receipt_ids],
        },
    )


def duplicate_invoice_exception(
    *,
    invoice: EngineInvoice,
    other_invoice_id: UUID,
    other_invoice_number: str,
) -> ExceptionDraft:
    return ExceptionDraft(
        exception_type=ExceptionType.DUPLICATE_INVOICE,
        severity=ExceptionSeverity.CRITICAL,
        message=(
            f"Duplicate invoice identity for vendor {invoice.vendor_id}: "
            f"'{invoice.invoice_number}' matches existing '{other_invoice_number}'."
        ),
        fingerprint=build_fingerprint(
            ExceptionType.DUPLICATE_INVOICE.value,
            invoice.vendor_id,
            normalize_invoice_number(invoice.invoice_number),
            invoice.id,
            other_invoice_id,
        ),
        invoice_id=invoice.id,
        purchase_order_id=invoice.purchase_order_id,
        source_document_ids=[invoice.id, other_invoice_id],
        evidence={
            "vendor_id": str(invoice.vendor_id),
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "normalized_invoice_number": normalize_invoice_number(invoice.invoice_number),
            "duplicate_invoice_id": str(other_invoice_id),
            "duplicate_invoice_number": other_invoice_number,
            "expected_value": "unique vendor + normalized invoice number",
            "actual_value": normalize_invoice_number(invoice.invoice_number),
        },
    )


__all__ = [
    "build_fingerprint",
    "check_header_po_reference",
    "date_exceptions",
    "duplicate_invoice_exception",
    "exceeds_percent_tolerance",
    "exceeds_quantity_tolerance",
    "match_line_to_po",
    "missing_document_exception",
    "normalize_invoice_number",
    "percent_variance",
    "price_exception_for_line",
    "quantity_exceptions_for_line",
    "tax_exception_for_line",
]
