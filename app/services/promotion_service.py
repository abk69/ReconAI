"""Promote reviewed extraction candidates into authoritative PO/GRN/Invoice rows.

This is the M5 trust boundary. M4 candidates are never written here without
human APPROVED or CORRECTED status. M2 reconciliation is untouched.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    Document,
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ReviewTask,
    Vendor,
)
from app.domain.enums import (
    DocumentStatus,
    DocumentType,
    GoodsReceiptStatus,
    InvoiceStatus,
    PurchaseOrderStatus,
    ReviewStatus,
)
from app.review.transitions import PROMOTABLE_STATUSES
from app.services.review_service import ReviewNotFoundError, ReviewService


class PromotionError(Exception):
    """Base promotion error."""


class PromotionNotAllowedError(PromotionError):
    """Candidate is not eligible for promotion."""


class PromotionValidationError(PromotionError):
    """Required fields missing or invalid for authoritative write."""


class PromotionService:
    """Transactional promotion of reviewed candidates to financial tables."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._reviews = ReviewService(session)

    def promote(self, task_id: UUID) -> ReviewTask:
        """Promote an APPROVED or CORRECTED review task.

        Idempotent: repeated calls return the already-promoted task.
        Failures roll back the entire transaction.
        """
        task = self._reviews.get_task(task_id)

        if task.promoted_entity_id is not None:
            return task

        status = ReviewStatus(task.status)
        if status not in PROMOTABLE_STATUSES:
            raise PromotionNotAllowedError(
                f"Review task status {status.value} is not eligible for promotion."
            )

        document = self._session.get(Document, task.document_id)
        if document is None:
            raise ReviewNotFoundError(f"Document {task.document_id} was not found.")

        candidate = task.reviewed_candidate
        if candidate is None and task.extraction_result is not None:
            candidate = task.extraction_result.candidate
        if not isinstance(candidate, dict):
            raise PromotionValidationError("No reviewed candidate available for promotion.")

        detected = (
            DocumentType(task.extraction_result.detected_type)
            if task.extraction_result is not None
            else DocumentType(document.document_type)
        )
        if detected is DocumentType.UNKNOWN:
            # Prefer document type if reviewer classified it.
            if document.document_type in DocumentType._value2member_map_:
                detected = DocumentType(document.document_type)
            if detected is DocumentType.UNKNOWN:
                raise PromotionValidationError(
                    "Cannot promote UNKNOWN document type; set document type first."
                )

        try:
            if detected is DocumentType.PO:
                entity_id = self._promote_po(document, candidate)
                entity_type = DocumentType.PO.value
            elif detected is DocumentType.GRN:
                entity_id = self._promote_grn(document, candidate)
                entity_type = DocumentType.GRN.value
            elif detected is DocumentType.INVOICE:
                entity_id = self._promote_invoice(document, candidate)
                entity_type = DocumentType.INVOICE.value
            else:
                raise PromotionValidationError(f"Unsupported document type {detected.value}.")

            task.promoted_entity_type = entity_type
            task.promoted_entity_id = entity_id
            task.promoted_at = datetime.now(UTC)
            document.status = DocumentStatus.READY_FOR_RECONCILIATION.value
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

        return self._reviews.get_task(task_id)

    def _promote_po(self, document: Document, candidate: dict[str, Any]) -> UUID:
        po_number = _require_str(candidate, "po_number")
        existing = self._session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.po_number == po_number)
        )
        if existing is not None:
            document.purchase_order_id = existing.id
            return existing.id

        vendor = self._resolve_vendor(document, candidate)
        order_date = _require_date(candidate, "order_date")
        currency = str(candidate.get("currency") or "USD").upper()
        lines = candidate.get("lines") or []
        if not lines:
            raise PromotionValidationError("Purchase order requires at least one line.")

        po = PurchaseOrder(
            po_number=po_number,
            vendor_id=vendor.id,
            order_date=order_date,
            currency=currency,
            status=PurchaseOrderStatus.OPEN.value,
        )
        for idx, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise PromotionValidationError("Invalid PO line payload.")
            po.lines.append(
                PurchaseOrderLine(
                    line_number=int(line.get("line_number") or idx),
                    description=line.get("description"),
                    quantity=_require_decimal(line, "quantity", positive=True),
                    unit_price=_require_decimal(line, "unit_price", non_negative=True),
                    tax_rate=_optional_decimal(line, "tax_rate", default=Decimal("0")),
                )
            )
        self._session.add(po)
        self._session.flush()
        document.purchase_order_id = po.id
        document.vendor_id = vendor.id
        return po.id

    def _promote_grn(self, document: Document, candidate: dict[str, Any]) -> UUID:
        grn_number = _require_str(candidate, "grn_number")
        existing = self._session.scalar(
            select(GoodsReceipt).where(GoodsReceipt.grn_number == grn_number)
        )
        if existing is not None:
            document.goods_receipt_id = existing.id
            return existing.id

        po = self._resolve_po(document, candidate)
        receipt_date = _require_date(candidate, "receipt_date")
        lines = candidate.get("lines") or []
        if not lines:
            raise PromotionValidationError("GRN requires at least one line.")

        grn = GoodsReceipt(
            grn_number=grn_number,
            purchase_order_id=po.id,
            receipt_date=receipt_date,
            status=GoodsReceiptStatus.POSTED.value,
        )
        po_lines = {line.line_number: line for line in po.lines}
        for idx, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise PromotionValidationError("Invalid GRN line payload.")
            qty = line.get("quantity")
            if qty is None and "received_quantity" in line:
                qty_source = {"quantity": line["received_quantity"]}
            else:
                qty_source = line
            line_number = int(line.get("line_number") or idx)
            po_line = po_lines.get(line_number)
            grn.lines.append(
                GoodsReceiptLine(
                    line_number=line_number,
                    received_quantity=_require_decimal(qty_source, "quantity", positive=True),
                    purchase_order_line_id=po_line.id if po_line else None,
                )
            )
        self._session.add(grn)
        self._session.flush()
        document.goods_receipt_id = grn.id
        document.purchase_order_id = po.id
        return grn.id

    def _promote_invoice(self, document: Document, candidate: dict[str, Any]) -> UUID:
        invoice_number = _require_str(candidate, "invoice_number")
        existing = self._session.scalar(
            select(Invoice).where(Invoice.invoice_number == invoice_number)
        )
        if existing is not None:
            document.invoice_id = existing.id
            return existing.id

        vendor = self._resolve_vendor(document, candidate)
        invoice_date = _require_date(candidate, "invoice_date")
        currency = str(candidate.get("currency") or "USD").upper()
        po: PurchaseOrder | None = None
        if candidate.get("po_number") or document.purchase_order_id is not None:
            po = self._resolve_po_optional(document, candidate)

        lines = candidate.get("lines") or []
        if not lines:
            raise PromotionValidationError("Invoice requires at least one line.")

        invoice = Invoice(
            invoice_number=invoice_number,
            vendor_id=vendor.id,
            purchase_order_id=po.id if po else None,
            invoice_date=invoice_date,
            currency=currency,
            status=InvoiceStatus.RECEIVED.value,
            subtotal=_optional_decimal(candidate, "subtotal", default=Decimal("0")),
            tax_amount=_optional_decimal(candidate, "tax_amount", default=Decimal("0")),
            total_amount=_optional_decimal(candidate, "total_amount", default=Decimal("0")),
        )
        po_line_by_number: dict[int, PurchaseOrderLine] = {}
        if po is not None:
            po_line_by_number = {line.line_number: line for line in po.lines}

        for idx, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise PromotionValidationError("Invalid invoice line payload.")
            line_number = int(line.get("line_number") or idx)
            po_line = po_line_by_number.get(line_number)
            invoice.lines.append(
                InvoiceLine(
                    line_number=line_number,
                    description=line.get("description"),
                    quantity=_require_decimal(line, "quantity", positive=True),
                    unit_price=_require_decimal(line, "unit_price", non_negative=True),
                    tax_rate=_optional_decimal(line, "tax_rate", default=Decimal("0")),
                    purchase_order_line_id=po_line.id if po_line else None,
                )
            )
        self._session.add(invoice)
        self._session.flush()
        document.invoice_id = invoice.id
        document.vendor_id = vendor.id
        if po is not None:
            document.purchase_order_id = po.id
        return invoice.id

    def _resolve_vendor(self, document: Document, candidate: dict[str, Any]) -> Vendor:
        if document.vendor_id is not None:
            vendor = self._session.get(Vendor, document.vendor_id)
            if vendor is not None:
                return vendor

        name = candidate.get("vendor_name")
        if isinstance(name, str) and name.strip():
            vendor = self._session.scalar(select(Vendor).where(Vendor.name == name.strip()))
            if vendor is not None:
                return vendor
            vendor = Vendor(name=name.strip())
            self._session.add(vendor)
            self._session.flush()
            return vendor

        raise PromotionValidationError(
            "vendor_id or vendor_name is required to promote this candidate."
        )

    def _resolve_po(self, document: Document, candidate: dict[str, Any]) -> PurchaseOrder:
        po = self._resolve_po_optional(document, candidate)
        if po is None:
            raise PromotionValidationError(
                "purchase_order_id or po_number is required to promote this GRN."
            )
        return po

    def _resolve_po_optional(
        self,
        document: Document,
        candidate: dict[str, Any],
    ) -> PurchaseOrder | None:
        if document.purchase_order_id is not None:
            po = self._session.scalar(
                select(PurchaseOrder)
                .where(PurchaseOrder.id == document.purchase_order_id)
                .options(selectinload(PurchaseOrder.lines))
            )
            if po is not None:
                return po

        po_number = candidate.get("po_number")
        if isinstance(po_number, str) and po_number.strip():
            return self._session.scalar(
                select(PurchaseOrder)
                .where(PurchaseOrder.po_number == po_number.strip())
                .options(selectinload(PurchaseOrder.lines))
            )
        return None


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PromotionValidationError(f"Missing required field: {key}")
    return value.strip()


def _require_date(data: dict[str, Any], key: str) -> date:
    value = data.get(key)
    if value is None:
        raise PromotionValidationError(f"Missing required field: {key}")
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise PromotionValidationError(f"Invalid date for {key}: {value!r}") from exc


def _require_decimal(
    data: dict[str, Any],
    key: str,
    *,
    positive: bool = False,
    non_negative: bool = False,
) -> Decimal:
    if key not in data or data[key] is None:
        raise PromotionValidationError(f"Missing required field: {key}")
    try:
        value = Decimal(str(data[key]))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PromotionValidationError(f"Invalid Decimal for {key}: {data[key]!r}") from exc
    if positive and value <= 0:
        raise PromotionValidationError(f"{key} must be positive.")
    if non_negative and value < 0:
        raise PromotionValidationError(f"{key} cannot be negative.")
    return value


def _optional_decimal(
    data: dict[str, Any],
    key: str,
    *,
    default: Decimal,
) -> Decimal:
    if key not in data or data[key] is None:
        return default
    try:
        value = Decimal(str(data[key]))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise PromotionValidationError(f"Invalid Decimal for {key}: {data[key]!r}") from exc
    if value < 0:
        raise PromotionValidationError(f"{key} cannot be negative.")
    return value
