"""Read-only list and search helpers for the procurement workspace."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ReconciliationException,
    Vendor,
)
from app.domain.enums import ExceptionStatus


def like_pattern(value: str) -> str:
    """Contains-match pattern with LIKE wildcards escaped."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _apply_like(column: object, value: str):
    return column.ilike(like_pattern(value), escape="\\")  # type: ignore[attr-defined]


def list_purchase_orders(
    session: Session,
    *,
    q: str | None,
    status: str | None,
    vendor_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    filters = []
    if q:
        filters.append(_apply_like(PurchaseOrder.po_number, q))
    if status:
        filters.append(PurchaseOrder.status == status)
    if vendor_id is not None:
        filters.append(PurchaseOrder.vendor_id == vendor_id)
    line_count = (
        select(func.count(PurchaseOrderLine.id))
        .where(PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .correlate(PurchaseOrder)
        .scalar_subquery()
    )
    base = select(PurchaseOrder, Vendor.name, line_count).join(
        Vendor, PurchaseOrder.vendor_id == Vendor.id
    )
    if filters:
        base = base.where(*filters)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.execute(
        base.order_by(PurchaseOrder.created_at.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        {
            "id": po.id,
            "po_number": po.po_number,
            "vendor_id": po.vendor_id,
            "vendor_name": vendor_name,
            "order_date": po.order_date,
            "currency": po.currency,
            "status": po.status,
            "line_count": int(count or 0),
            "created_at": po.created_at,
        }
        for po, vendor_name, count in rows
    ]
    return items, total


def list_goods_receipts(
    session: Session,
    *,
    q: str | None,
    status: str | None,
    purchase_order_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    filters = []
    if q:
        filters.append(_apply_like(GoodsReceipt.grn_number, q))
    if status:
        filters.append(GoodsReceipt.status == status)
    if purchase_order_id is not None:
        filters.append(GoodsReceipt.purchase_order_id == purchase_order_id)
    line_count = (
        select(func.count(GoodsReceiptLine.id))
        .where(GoodsReceiptLine.goods_receipt_id == GoodsReceipt.id)
        .correlate(GoodsReceipt)
        .scalar_subquery()
    )
    base = select(GoodsReceipt, PurchaseOrder.po_number, line_count).join(
        PurchaseOrder, GoodsReceipt.purchase_order_id == PurchaseOrder.id
    )
    if filters:
        base = base.where(*filters)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.execute(
        base.order_by(GoodsReceipt.created_at.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        {
            "id": grn.id,
            "grn_number": grn.grn_number,
            "purchase_order_id": grn.purchase_order_id,
            "po_number": po_number,
            "receipt_date": grn.receipt_date,
            "status": grn.status,
            "line_count": int(count or 0),
            "created_at": grn.created_at,
        }
        for grn, po_number, count in rows
    ]
    return items, total


def list_invoices(
    session: Session,
    *,
    q: str | None,
    status: str | None,
    vendor_id: UUID | None,
    purchase_order_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    filters = []
    if q:
        filters.append(_apply_like(Invoice.invoice_number, q))
    if status:
        filters.append(Invoice.status == status)
    if vendor_id is not None:
        filters.append(Invoice.vendor_id == vendor_id)
    if purchase_order_id is not None:
        filters.append(Invoice.purchase_order_id == purchase_order_id)
    line_count = (
        select(func.count(InvoiceLine.id))
        .where(InvoiceLine.invoice_id == Invoice.id)
        .correlate(Invoice)
        .scalar_subquery()
    )
    base = (
        select(Invoice, Vendor.name, PurchaseOrder.po_number, line_count)
        .join(Vendor, Invoice.vendor_id == Vendor.id)
        .outerjoin(PurchaseOrder, Invoice.purchase_order_id == PurchaseOrder.id)
    )
    if filters:
        base = base.where(*filters)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.execute(
        base.order_by(Invoice.created_at.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "vendor_id": invoice.vendor_id,
            "vendor_name": vendor_name,
            "purchase_order_id": invoice.purchase_order_id,
            "po_number": po_number,
            "invoice_date": invoice.invoice_date,
            "currency": invoice.currency,
            "status": invoice.status,
            "total_amount": invoice.total_amount,
            "line_count": int(count or 0),
            "created_at": invoice.created_at,
        }
        for invoice, vendor_name, po_number, count in rows
    ]
    return items, total


def _exception_filters(
    *,
    q: str | None,
    severity: str | None,
    exception_type: str | None,
    invoice_id: UUID | None,
    purchase_order_id: UUID | None,
    goods_receipt_id: UUID | None,
    status: str | None,
) -> list[object]:
    filters: list[object] = []
    if severity:
        filters.append(ReconciliationException.severity == severity)
    if exception_type:
        filters.append(ReconciliationException.exception_type == exception_type)
    if invoice_id is not None:
        filters.append(ReconciliationException.invoice_id == invoice_id)
    if purchase_order_id is not None:
        filters.append(ReconciliationException.purchase_order_id == purchase_order_id)
    if goods_receipt_id is not None:
        filters.append(ReconciliationException.goods_receipt_id == goods_receipt_id)
    if status:
        filters.append(ReconciliationException.status == status)
    if q:
        pattern = like_pattern(q)
        filters.append(
            or_(
                Invoice.invoice_number.ilike(pattern, escape="\\"),
                PurchaseOrder.po_number.ilike(pattern, escape="\\"),
                GoodsReceipt.grn_number.ilike(pattern, escape="\\"),
            )
        )
    return filters


def _exception_base():
    return (
        select(
            ReconciliationException,
            Invoice.invoice_number,
            PurchaseOrder.po_number,
            GoodsReceipt.grn_number,
        )
        .outerjoin(Invoice, ReconciliationException.invoice_id == Invoice.id)
        .outerjoin(PurchaseOrder, ReconciliationException.purchase_order_id == PurchaseOrder.id)
        .outerjoin(GoodsReceipt, ReconciliationException.goods_receipt_id == GoodsReceipt.id)
    )


def list_exceptions(
    session: Session,
    *,
    q: str | None,
    status: str | None,
    severity: str | None,
    exception_type: str | None,
    invoice_id: UUID | None,
    purchase_order_id: UUID | None,
    goods_receipt_id: UUID | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int, dict[str, int]]:
    shared = _exception_filters(
        q=q,
        severity=severity,
        exception_type=exception_type,
        invoice_id=invoice_id,
        purchase_order_id=purchase_order_id,
        goods_receipt_id=goods_receipt_id,
        status=None,
    )
    status_stmt = (
        select(ReconciliationException.status, func.count())
        .select_from(ReconciliationException)
        .outerjoin(Invoice, ReconciliationException.invoice_id == Invoice.id)
        .outerjoin(PurchaseOrder, ReconciliationException.purchase_order_id == PurchaseOrder.id)
        .outerjoin(GoodsReceipt, ReconciliationException.goods_receipt_id == GoodsReceipt.id)
    )
    if shared:
        status_stmt = status_stmt.where(*shared)
    status_rows = session.execute(status_stmt.group_by(ReconciliationException.status)).all()
    counts = {item.value: 0 for item in ExceptionStatus}
    for value, count in status_rows:
        counts[str(value)] = int(count)

    filters = _exception_filters(
        q=q,
        severity=severity,
        exception_type=exception_type,
        invoice_id=invoice_id,
        purchase_order_id=purchase_order_id,
        goods_receipt_id=goods_receipt_id,
        status=status,
    )
    base = _exception_base()
    if filters:
        base = base.where(*filters)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = session.execute(
        base.order_by(ReconciliationException.created_at.desc()).limit(limit).offset(offset)
    ).all()
    items = [
        {
            "id": row.id,
            "exception_type": row.exception_type,
            "severity": row.severity,
            "status": row.status,
            "message": row.message,
            "invoice_id": row.invoice_id,
            "invoice_number": invoice_number,
            "purchase_order_id": row.purchase_order_id,
            "po_number": po_number,
            "goods_receipt_id": row.goods_receipt_id,
            "grn_number": grn_number,
            "created_at": row.created_at,
        }
        for row, invoice_number, po_number, grn_number in rows
    ]
    return items, total, counts


def get_exception(session: Session, exception_id: UUID) -> dict[str, object] | None:
    row = session.execute(
        _exception_base().where(ReconciliationException.id == exception_id)
    ).one_or_none()
    if row is None:
        return None
    exception, invoice_number, po_number, grn_number = row
    return {
        "id": exception.id,
        "exception_type": exception.exception_type,
        "severity": exception.severity,
        "status": exception.status,
        "message": exception.message,
        "invoice_id": exception.invoice_id,
        "invoice_number": invoice_number,
        "purchase_order_id": exception.purchase_order_id,
        "po_number": po_number,
        "goods_receipt_id": exception.goods_receipt_id,
        "grn_number": grn_number,
        "source_document_ids": list(exception.source_document_ids or []),
        "evidence": dict(exception.evidence or {}),
        "created_at": exception.created_at,
        "resolved_at": exception.resolved_at,
    }
