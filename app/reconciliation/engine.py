"""Deterministic reconciliation engine.

Orchestrates pure rules over structured procurement documents. Independent of
FastAPI, SQLAlchemy, and any AI services.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from uuid import UUID

from app.domain.enums import ExceptionType, ReconciliationStatus
from app.reconciliation.rules import (
    check_header_po_reference,
    date_exceptions,
    duplicate_invoice_exception,
    match_line_to_po,
    missing_document_exception,
    normalize_invoice_number,
    price_exception_for_line,
    quantity_exceptions_for_line,
    tax_exception_for_line,
)
from app.reconciliation.schemas import (
    ExceptionDraft,
    ReconciliationInput,
    ReconciliationResult,
    ReconciliationSummary,
)


def _dedupe_drafts(drafts: list[ExceptionDraft]) -> list[ExceptionDraft]:
    seen: set[str] = set()
    unique: list[ExceptionDraft] = []
    for draft in drafts:
        if draft.fingerprint in seen:
            continue
        seen.add(draft.fingerprint)
        unique.append(draft)
    return unique


def _collect_document_ids(payload: ReconciliationInput) -> list[UUID]:
    ids: list[UUID] = []
    if payload.purchase_order is not None:
        ids.append(payload.purchase_order.id)
    ids.extend(grn.id for grn in payload.goods_receipts)
    if payload.invoice is not None:
        ids.append(payload.invoice.id)
    return ids


def _build_summary(
    payload: ReconciliationInput,
    drafts: list[ExceptionDraft],
    received_by_po_line: dict[UUID, Decimal],
    invoiced_by_po_line: dict[UUID, Decimal],
) -> ReconciliationSummary:
    by_type: dict[str, int] = defaultdict(int)
    for draft in drafts:
        by_type[draft.exception_type.value] += 1

    ordered = Decimal("0")
    if payload.purchase_order is not None:
        ordered = sum((line.quantity for line in payload.purchase_order.lines), Decimal("0"))

    return ReconciliationSummary(
        exception_count_by_type=dict(by_type),
        po_line_count=len(payload.purchase_order.lines) if payload.purchase_order else 0,
        grn_count=len(payload.goods_receipts),
        invoice_line_count=len(payload.invoice.lines) if payload.invoice else 0,
        total_ordered_quantity=ordered,
        total_received_quantity=sum(received_by_po_line.values(), Decimal("0")),
        total_invoiced_quantity=sum(invoiced_by_po_line.values(), Decimal("0")),
    )


def _resolve_status(
    drafts: list[ExceptionDraft],
    *,
    incomplete: bool,
) -> ReconciliationStatus:
    if incomplete or any(d.exception_type is ExceptionType.MISSING_DOCUMENT for d in drafts):
        return ReconciliationStatus.INCOMPLETE
    if drafts:
        return ReconciliationStatus.EXCEPTIONS_FOUND
    return ReconciliationStatus.MATCHED


def reconcile(payload: ReconciliationInput) -> ReconciliationResult:
    """Run deterministic reconciliation and return structured exceptions."""
    drafts: list[ExceptionDraft] = []
    received_by_po_line: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    invoiced_by_po_line: dict[UUID, Decimal] = defaultdict(lambda: Decimal("0"))
    grn_lines_by_po_line: dict[UUID, list[UUID]] = defaultdict(list)
    invoice_lines_by_po_line: dict[UUID, list[UUID]] = defaultdict(list)
    incomplete = False

    po = payload.purchase_order
    invoice = payload.invoice
    grns = payload.goods_receipts
    config = payload.config

    # --- Empty / invalid input -------------------------------------------------
    if po is None and invoice is None and not grns:
        drafts.append(
            missing_document_exception(
                missing="PO",
                purchase_order_id=None,
                invoice_id=None,
                goods_receipt_ids=[],
                source_document_ids=[],
            )
        )
        incomplete = True
        return ReconciliationResult(
            status=ReconciliationStatus.INCOMPLETE,
            exception_count=len(drafts),
            exceptions=drafts,
            summary=_build_summary(payload, drafts, received_by_po_line, invoiced_by_po_line),
            document_ids=_collect_document_ids(payload),
            purchase_order_id=None,
            invoice_id=None,
            goods_receipt_ids=[],
        )

    # --- Missing documents (do not invent qty/price mismatches) ----------------
    if po is None:
        drafts.append(
            missing_document_exception(
                missing="PO",
                purchase_order_id=None,
                invoice_id=invoice.id if invoice else None,
                goods_receipt_ids=[g.id for g in grns],
                source_document_ids=_collect_document_ids(payload),
            )
        )
        incomplete = True

    if invoice is None:
        drafts.append(
            missing_document_exception(
                missing="INVOICE",
                purchase_order_id=po.id if po else None,
                invoice_id=None,
                goods_receipt_ids=[g.id for g in grns],
                source_document_ids=_collect_document_ids(payload),
            )
        )
        incomplete = True

    if po is not None and invoice is not None and not grns:
        drafts.append(
            missing_document_exception(
                missing="GRN",
                purchase_order_id=po.id,
                invoice_id=invoice.id,
                goods_receipt_ids=[],
                source_document_ids=[po.id, invoice.id],
            )
        )
        incomplete = True

    # --- Duplicate invoice identity -------------------------------------------
    if invoice is not None:
        normalized = normalize_invoice_number(invoice.invoice_number)
        for candidate in payload.duplicate_candidates:
            if candidate.id == invoice.id:
                continue
            if candidate.vendor_id != invoice.vendor_id:
                continue
            if normalize_invoice_number(candidate.invoice_number) == normalized:
                drafts.append(
                    duplicate_invoice_exception(
                        invoice=invoice,
                        other_invoice_id=candidate.id,
                        other_invoice_number=candidate.invoice_number,
                    )
                )

    # Without a PO we cannot line-match; return incomplete facts only.
    if po is None:
        unique = _dedupe_drafts(drafts)
        return ReconciliationResult(
            status=_resolve_status(unique, incomplete=True),
            exception_count=len(unique),
            exceptions=unique,
            summary=_build_summary(payload, unique, received_by_po_line, invoiced_by_po_line),
            document_ids=_collect_document_ids(payload),
            purchase_order_id=None,
            invoice_id=invoice.id if invoice else None,
            goods_receipt_ids=[g.id for g in grns],
        )

    # --- Header identifier + date checks --------------------------------------
    for grn in grns:
        header_exc = check_header_po_reference(
            purchase_order=po,
            referenced_po_id=grn.purchase_order_id,
            document_label="GRN",
            document_id=grn.id,
        )
        if header_exc is not None:
            drafts.append(header_exc)

    if invoice is not None:
        header_exc = check_header_po_reference(
            purchase_order=po,
            referenced_po_id=invoice.purchase_order_id,
            document_label="Invoice",
            document_id=invoice.id,
        )
        if header_exc is not None:
            drafts.append(header_exc)

    drafts.extend(date_exceptions(purchase_order=po, goods_receipts=grns, invoice=invoice))

    # --- Match GRN lines and aggregate received qty across all GRNs -----------
    for grn in grns:
        for grn_line in grn.lines:
            po_line, match_exc = match_line_to_po(
                purchase_order=po,
                purchase_order_line_id=grn_line.purchase_order_line_id,
                line_number=grn_line.line_number,
                document_label="GRN",
                document_id=grn.id,
                line_id=grn_line.id,
            )
            if match_exc is not None:
                drafts.append(match_exc)
                continue
            assert po_line is not None
            received_by_po_line[po_line.id] += grn_line.received_quantity
            grn_lines_by_po_line[po_line.id].append(grn_line.id)

    # --- Match invoice lines --------------------------------------------------
    if invoice is not None:
        for inv_line in invoice.lines:
            po_line, match_exc = match_line_to_po(
                purchase_order=po,
                purchase_order_line_id=inv_line.purchase_order_line_id,
                line_number=inv_line.line_number,
                document_label="Invoice",
                document_id=invoice.id,
                line_id=inv_line.id,
            )
            if match_exc is not None:
                drafts.append(match_exc)
                continue
            assert po_line is not None
            invoiced_by_po_line[po_line.id] += inv_line.quantity
            invoice_lines_by_po_line[po_line.id].append(inv_line.id)

            price_exc = price_exception_for_line(
                purchase_order=po,
                po_line=po_line,
                invoice=invoice,
                invoice_line=inv_line,
                config=config,
            )
            if price_exc is not None:
                drafts.append(price_exc)

            tax_exc = tax_exception_for_line(
                purchase_order=po,
                po_line=po_line,
                invoice=invoice,
                invoice_line=inv_line,
                config=config,
            )
            if tax_exc is not None:
                drafts.append(tax_exc)

    # --- Quantity rules (skip when GRN evidence is missing) -------------------
    if grns and invoice is not None:
        grn_ids = [g.id for g in grns]
        for po_line in po.lines:
            received = received_by_po_line.get(po_line.id, Decimal("0"))
            invoiced = invoiced_by_po_line.get(po_line.id, Decimal("0"))
            # Lines with no receipt and no invoice activity are fine (unordered).
            if received == 0 and invoiced == 0:
                continue
            drafts.extend(
                quantity_exceptions_for_line(
                    purchase_order=po,
                    po_line=po_line,
                    received_quantity=received,
                    invoiced_quantity=invoiced,
                    grn_line_ids=grn_lines_by_po_line.get(po_line.id, []),
                    invoice_line_ids=invoice_lines_by_po_line.get(po_line.id, []),
                    invoice_id=invoice.id,
                    goods_receipt_ids=grn_ids,
                    config=config,
                )
            )

    unique = _dedupe_drafts(drafts)
    status = _resolve_status(unique, incomplete=incomplete)
    return ReconciliationResult(
        status=status,
        exception_count=len(unique),
        exceptions=unique,
        summary=_build_summary(payload, unique, received_by_po_line, invoiced_by_po_line),
        document_ids=_collect_document_ids(payload),
        purchase_order_id=po.id,
        invoice_id=invoice.id if invoice else None,
        goods_receipt_ids=[g.id for g in grns],
    )
