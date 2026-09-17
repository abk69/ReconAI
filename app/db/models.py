"""SQLAlchemy ORM models for the procurement domain.

These tables store the financial facts that the deterministic reconciliation
engine will consume. Monetary columns use ``Numeric`` (never float).
Evidence is stored as JSON/JSONB for auditability.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.db.base import Base
from app.domain.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    GoodsReceiptStatus,
    InvoiceStatus,
    PurchaseOrderStatus,
)

# PostgreSQL uses JSONB; SQLite tests use JSON via dialect variant.
JsonDocument = JSONB().with_variant(JSON(), "sqlite")

Money = Numeric(18, 4)
Quantity = Numeric(18, 4)
TaxRate = Numeric(8, 4)


class Vendor(Base):
    """Supplier / vendor master record."""

    __tablename__ = "vendors"
    __table_args__ = (Index("ix_vendors_tax_id", "tax_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    tax_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    purchase_orders: Mapped[list[PurchaseOrder]] = relationship(back_populates="vendor")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="vendor")


class PurchaseOrder(Base):
    """Purchase order header."""

    __tablename__ = "purchase_orders"
    __table_args__ = (
        UniqueConstraint("po_number", name="uq_purchase_orders_po_number"),
        Index("ix_purchase_orders_po_number", "po_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    po_number: Mapped[str] = mapped_column(String(64), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PurchaseOrderStatus.OPEN.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    vendor: Mapped[Vendor] = relationship(back_populates="purchase_orders")
    lines: Mapped[list[PurchaseOrderLine]] = relationship(
        back_populates="purchase_order",
        cascade="all, delete-orphan",
    )
    goods_receipts: Mapped[list[GoodsReceipt]] = relationship(back_populates="purchase_order")
    invoices: Mapped[list[Invoice]] = relationship(back_populates="purchase_order")


class PurchaseOrderLine(Base):
    """Purchase order line item."""

    __tablename__ = "purchase_order_lines"
    __table_args__ = (
        UniqueConstraint(
            "purchase_order_id",
            "line_number",
            name="uq_purchase_order_lines_po_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("purchase_orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(TaxRate, nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="lines")
    goods_receipt_lines: Mapped[list[GoodsReceiptLine]] = relationship(
        back_populates="purchase_order_line",
    )
    invoice_lines: Mapped[list[InvoiceLine]] = relationship(back_populates="purchase_order_line")


class GoodsReceipt(Base):
    """Goods receipt note (GRN) header."""

    __tablename__ = "goods_receipts"
    __table_args__ = (
        UniqueConstraint("grn_number", name="uq_goods_receipts_grn_number"),
        Index("ix_goods_receipts_grn_number", "grn_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    grn_number: Mapped[str] = mapped_column(String(64), nullable=False)
    purchase_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("purchase_orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    receipt_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=GoodsReceiptStatus.POSTED.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    purchase_order: Mapped[PurchaseOrder] = relationship(back_populates="goods_receipts")
    lines: Mapped[list[GoodsReceiptLine]] = relationship(
        back_populates="goods_receipt",
        cascade="all, delete-orphan",
    )


class GoodsReceiptLine(Base):
    """Goods receipt line item."""

    __tablename__ = "goods_receipt_lines"
    __table_args__ = (
        UniqueConstraint(
            "goods_receipt_id",
            "line_number",
            name="uq_goods_receipt_lines_grn_line",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    goods_receipt_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("goods_receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("purchase_order_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    received_quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    goods_receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")
    purchase_order_line: Mapped[PurchaseOrderLine | None] = relationship(
        back_populates="goods_receipt_lines",
    )


class Invoice(Base):
    """Vendor invoice header."""

    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
        Index("ix_invoices_invoice_number", "invoice_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    invoice_number: Mapped[str] = mapped_column(String(64), nullable=False)
    vendor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("vendors.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_date: Mapped[date] = mapped_column(Date, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=InvoiceStatus.RECEIVED.value,
    )
    subtotal: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    vendor: Mapped[Vendor] = relationship(back_populates="invoices")
    purchase_order: Mapped[PurchaseOrder | None] = relationship(back_populates="invoices")
    lines: Mapped[list[InvoiceLine]] = relationship(
        back_populates="invoice",
        cascade="all, delete-orphan",
    )


class InvoiceLine(Base):
    """Vendor invoice line item."""

    __tablename__ = "invoice_lines"
    __table_args__ = (
        UniqueConstraint("invoice_id", "line_number", name="uq_invoice_lines_invoice_line"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purchase_order_line_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("purchase_order_lines.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tax_rate: Mapped[Decimal] = mapped_column(TaxRate, nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    purchase_order_line: Mapped[PurchaseOrderLine | None] = relationship(
        back_populates="invoice_lines",
    )


class ReconciliationException(Base):
    """Exception raised by deterministic reconciliation, with preserved evidence."""

    __tablename__ = "reconciliation_exceptions"
    __table_args__ = (Index("ix_reconciliation_exceptions_status", "status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exception_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ExceptionStatus.OPEN.value,
    )
    purchase_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("purchase_orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    goods_receipt_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("goods_receipts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("invoices.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Additional document UUIDs beyond the typed FK references above.
    source_document_ids: Mapped[list[Any]] = mapped_column(
        JsonDocument,
        nullable=False,
        default=list,
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JsonDocument,
        nullable=False,
        default=dict,
    )
    # Stable identity for idempotent upserts across re-runs of the same facts.
    fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    purchase_order: Mapped[PurchaseOrder | None] = relationship()
    goods_receipt: Mapped[GoodsReceipt | None] = relationship()
    invoice: Mapped[Invoice | None] = relationship()


# Re-export enum names for callers that want ORM + domain enums together.
__all__ = [
    "Vendor",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "GoodsReceipt",
    "GoodsReceiptLine",
    "Invoice",
    "InvoiceLine",
    "ReconciliationException",
    "ExceptionSeverity",
    "ExceptionStatus",
    "ExceptionType",
    "GoodsReceiptStatus",
    "InvoiceStatus",
    "PurchaseOrderStatus",
]
