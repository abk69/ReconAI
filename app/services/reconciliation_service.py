"""Service that loads persistence data, runs the engine, and upserts exceptions."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.models import (
    GoodsReceipt,
    Invoice,
    PurchaseOrder,
    ReconciliationException,
)
from app.domain.enums import ExceptionStatus
from app.reconciliation.engine import reconcile
from app.reconciliation.rules import normalize_invoice_number
from app.reconciliation.schemas import (
    DuplicateInvoiceCandidate,
    EngineGoodsReceipt,
    EngineGoodsReceiptLine,
    EngineInvoice,
    EngineInvoiceLine,
    EnginePurchaseOrder,
    EnginePurchaseOrderLine,
    ExceptionDraft,
    ReconciliationConfig,
    ReconciliationInput,
    ReconciliationResult,
)


class ReconciliationServiceError(Exception):
    """Base error for reconciliation service failures."""


class ReconciliationNotFoundError(ReconciliationServiceError):
    """Raised when a requested document cannot be loaded."""


def _to_engine_po(po: PurchaseOrder) -> EnginePurchaseOrder:
    return EnginePurchaseOrder(
        id=po.id,
        po_number=po.po_number,
        vendor_id=po.vendor_id,
        order_date=po.order_date,
        currency=po.currency,
        lines=[
            EnginePurchaseOrderLine(
                id=line.id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
            )
            for line in po.lines
        ],
    )


def _to_engine_grn(grn: GoodsReceipt) -> EngineGoodsReceipt:
    return EngineGoodsReceipt(
        id=grn.id,
        grn_number=grn.grn_number,
        purchase_order_id=grn.purchase_order_id,
        receipt_date=grn.receipt_date,
        lines=[
            EngineGoodsReceiptLine(
                id=line.id,
                line_number=line.line_number,
                received_quantity=line.received_quantity,
                purchase_order_line_id=line.purchase_order_line_id,
            )
            for line in grn.lines
        ],
    )


def _to_engine_invoice(invoice: Invoice) -> EngineInvoice:
    return EngineInvoice(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        vendor_id=invoice.vendor_id,
        purchase_order_id=invoice.purchase_order_id,
        invoice_date=invoice.invoice_date,
        currency=invoice.currency,
        lines=[
            EngineInvoiceLine(
                id=line.id,
                line_number=line.line_number,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_rate=line.tax_rate,
                purchase_order_line_id=line.purchase_order_line_id,
            )
            for line in invoice.lines
        ],
    )


def _default_config(
    quantity_tolerance: Decimal | None = None,
    price_tolerance_percent: Decimal | None = None,
    tax_rate_tolerance_percent: Decimal | None = None,
) -> ReconciliationConfig:
    settings = get_settings()
    return ReconciliationConfig(
        quantity_tolerance=(
            quantity_tolerance
            if quantity_tolerance is not None
            else Decimal(settings.quantity_tolerance)
        ),
        price_tolerance_percent=(
            price_tolerance_percent
            if price_tolerance_percent is not None
            else Decimal(settings.price_tolerance_percent)
        ),
        tax_rate_tolerance_percent=(
            tax_rate_tolerance_percent
            if tax_rate_tolerance_percent is not None
            else Decimal(settings.tax_rate_tolerance_percent)
        ),
    )


def _find_duplicate_candidates(
    session: Session, invoice: Invoice
) -> list[DuplicateInvoiceCandidate]:
    """Find other invoices for the same vendor with a matching normalized number."""
    normalized = normalize_invoice_number(invoice.invoice_number)
    rows = session.scalars(
        select(Invoice).where(
            Invoice.vendor_id == invoice.vendor_id,
            Invoice.id != invoice.id,
        )
    ).all()
    candidates: list[DuplicateInvoiceCandidate] = []
    for row in rows:
        if normalize_invoice_number(row.invoice_number) == normalized:
            candidates.append(
                DuplicateInvoiceCandidate(
                    id=row.id,
                    vendor_id=row.vendor_id,
                    invoice_number=row.invoice_number,
                )
            )
    return candidates


def _upsert_exceptions(
    session: Session,
    drafts: list[ExceptionDraft],
) -> list[ReconciliationException]:
    """Insert new exceptions or refresh existing open ones with the same fingerprint."""
    persisted: list[ReconciliationException] = []
    for draft in drafts:
        existing = session.scalar(
            select(ReconciliationException).where(
                ReconciliationException.fingerprint == draft.fingerprint
            )
        )
        if existing is not None:
            existing.exception_type = draft.exception_type.value
            existing.severity = draft.severity.value
            existing.message = draft.message
            existing.purchase_order_id = draft.purchase_order_id
            existing.goods_receipt_id = draft.goods_receipt_id
            existing.invoice_id = draft.invoice_id
            existing.source_document_ids = [str(i) for i in draft.source_document_ids]
            existing.evidence = draft.evidence
            if existing.status == ExceptionStatus.RESOLVED.value:
                # Re-detected after resolve: reopen for human review.
                existing.status = ExceptionStatus.OPEN.value
                existing.resolved_at = None
            persisted.append(existing)
            continue

        row = ReconciliationException(
            exception_type=draft.exception_type.value,
            severity=draft.severity.value,
            message=draft.message,
            status=ExceptionStatus.OPEN.value,
            purchase_order_id=draft.purchase_order_id,
            goods_receipt_id=draft.goods_receipt_id,
            invoice_id=draft.invoice_id,
            source_document_ids=[str(i) for i in draft.source_document_ids],
            evidence=draft.evidence,
            fingerprint=draft.fingerprint,
        )
        session.add(row)
        persisted.append(row)

    session.flush()
    return persisted


class ReconciliationService:
    """Application service for PO ↔ GRN ↔ Invoice reconciliation."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def run(
        self,
        *,
        purchase_order_id: UUID | None = None,
        invoice_id: UUID | None = None,
        quantity_tolerance: Decimal | None = None,
        price_tolerance_percent: Decimal | None = None,
        tax_rate_tolerance_percent: Decimal | None = None,
        persist: bool = True,
    ) -> ReconciliationResult:
        """Load documents, run the engine, and optionally persist exceptions."""
        if purchase_order_id is None and invoice_id is None:
            raise ReconciliationServiceError(
                "At least one of purchase_order_id or invoice_id is required."
            )

        po: PurchaseOrder | None = None
        invoice: Invoice | None = None
        grns: list[GoodsReceipt] = []

        if purchase_order_id is not None:
            po = self._session.scalar(
                select(PurchaseOrder)
                .where(PurchaseOrder.id == purchase_order_id)
                .options(selectinload(PurchaseOrder.lines))
            )
            if po is None:
                raise ReconciliationNotFoundError(
                    f"Purchase order {purchase_order_id} was not found."
                )
            grns = list(
                self._session.scalars(
                    select(GoodsReceipt)
                    .where(GoodsReceipt.purchase_order_id == purchase_order_id)
                    .options(selectinload(GoodsReceipt.lines))
                ).all()
            )

        if invoice_id is not None:
            invoice = self._session.scalar(
                select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.lines))
            )
            if invoice is None:
                raise ReconciliationNotFoundError(f"Invoice {invoice_id} was not found.")

            if po is None and invoice.purchase_order_id is not None:
                po = self._session.scalar(
                    select(PurchaseOrder)
                    .where(PurchaseOrder.id == invoice.purchase_order_id)
                    .options(selectinload(PurchaseOrder.lines))
                )
                if po is not None:
                    grns = list(
                        self._session.scalars(
                            select(GoodsReceipt)
                            .where(GoodsReceipt.purchase_order_id == po.id)
                            .options(selectinload(GoodsReceipt.lines))
                        ).all()
                    )

        duplicate_candidates: list[DuplicateInvoiceCandidate] = []
        if invoice is not None:
            duplicate_candidates = _find_duplicate_candidates(self._session, invoice)

        payload = ReconciliationInput(
            purchase_order=_to_engine_po(po) if po else None,
            goods_receipts=[_to_engine_grn(g) for g in grns],
            invoice=_to_engine_invoice(invoice) if invoice else None,
            duplicate_candidates=duplicate_candidates,
            config=_default_config(
                quantity_tolerance=quantity_tolerance,
                price_tolerance_percent=price_tolerance_percent,
                tax_rate_tolerance_percent=tax_rate_tolerance_percent,
            ),
        )
        result = reconcile(payload)

        if persist:
            _upsert_exceptions(self._session, result.exceptions)
            self._session.commit()

        return result
