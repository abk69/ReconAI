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

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
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
    ActionType,
    ApprovalDecision,
    DocumentStatus,
    DocumentType,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ExecutionStatus,
    GoodsReceiptStatus,
    InvoiceStatus,
    PolicyVersionStatus,
    ProposedActionStatus,
    PurchaseOrderStatus,
    ResolutionPlanStatus,
    ReviewAction,
    ReviewPriority,
    ReviewStatus,
)
from app.embeddings.constants import DEFAULT_EMBEDDING_DIMENSION

# PostgreSQL uses JSONB; SQLite tests use JSON via dialect variant.
JsonDocument = JSONB().with_variant(JSON(), "sqlite")

# pgvector on PostgreSQL; JSON float arrays on SQLite (offline tests).
# Dimension must match DEFAULT_EMBEDDING_DIMENSION / migration 0008.
PolicyEmbeddingVector = Vector(DEFAULT_EMBEDDING_DIMENSION).with_variant(JSON(), "sqlite")

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


class Document(Base):
    """Uploaded file metadata. Binary content lives on the filesystem."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_sha256", "sha256"),
        Index("ix_documents_document_type", "document_type"),
        Index("ix_documents_status", "status"),
        UniqueConstraint("sha256", name="uq_documents_sha256"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=DocumentType.UNKNOWN.value,
    )
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_extension: Mapped[str] = mapped_column(String(16), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DocumentStatus.VALIDATED.value,
    )
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("vendors.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    vendor: Mapped[Vendor | None] = relationship()
    purchase_order: Mapped[PurchaseOrder | None] = relationship()
    goods_receipt: Mapped[GoodsReceipt | None] = relationship()
    invoice: Mapped[Invoice | None] = relationship()
    extraction_result: Mapped[DocumentExtractionResult | None] = relationship(
        back_populates="document",
        uselist=False,
    )
    review_tasks: Mapped[list[ReviewTask]] = relationship(back_populates="document")


class DocumentExtractionResult(Base):
    """Persisted M4 understanding output — not authoritative financial truth.

    Structured candidates and evidence live in JSON so M4 can evolve without
    writing unvalidated values into PO/GRN/Invoice tables.
    """

    __tablename__ = "document_extraction_results"
    __table_args__ = (
        UniqueConstraint("document_id", name="uq_document_extraction_results_document_id"),
        Index("ix_document_extraction_results_outcome", "outcome"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    detected_type: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(32), nullable=False, default="m4-1.0")
    raw_extraction: Mapped[dict[str, Any]] = mapped_column(
        JsonDocument,
        nullable=False,
        default=dict,
    )
    candidate: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    validation: Mapped[dict[str, Any]] = mapped_column(
        JsonDocument,
        nullable=False,
        default=dict,
    )
    evidence: Mapped[list[Any]] = mapped_column(JsonDocument, nullable=False, default=list)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    document: Mapped[Document] = relationship(back_populates="extraction_result")
    review_tasks: Mapped[list[ReviewTask]] = relationship(back_populates="extraction_result")
    llm_results: Mapped[list[LlmExtractionResult]] = relationship(
        back_populates="m4_extraction_result",
    )


class LlmExtractionResult(Base):
    """Persisted M6 Gemini-assisted extraction — never overwrites M4.

    Gemini candidates are untrusted. Authoritative writes still require M5
    review + PromotionService.
    """

    __tablename__ = "llm_extraction_results"
    __table_args__ = (Index("ix_llm_extraction_results_invocation_status", "invocation_status"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    m4_extraction_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("document_extraction_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False, default="google")
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False, default="m6-1.0")
    invocation_status: Mapped[str] = mapped_column(String(64), nullable=False)
    application_quality: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quality_reasons: Mapped[list[Any]] = mapped_column(JsonDocument, nullable=False, default=list)
    gate_reasons: Mapped[list[Any]] = mapped_column(JsonDocument, nullable=False, default=list)
    candidate: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    evidence: Mapped[list[Any]] = mapped_column(JsonDocument, nullable=False, default=list)
    validation: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    comparison: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    evidence_check: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    usage: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonDocument,
        nullable=False,
        default=dict,
    )
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    document: Mapped[Document] = relationship()
    m4_extraction_result: Mapped[DocumentExtractionResult | None] = relationship(
        back_populates="llm_results",
    )


class ReviewTask(Base):
    """Human review queue item for an untrusted M4 extraction candidate.

    One active task per extraction result. Original extraction rows are never
    mutated; corrections live in ``reviewed_candidate`` and ``ReviewDecision``.
    """

    __tablename__ = "review_tasks"
    __table_args__ = (
        UniqueConstraint(
            "extraction_result_id",
            name="uq_review_tasks_extraction_result_id",
        ),
        Index("ix_review_tasks_status", "status"),
        Index("ix_review_tasks_priority", "priority"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extraction_result_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("document_extraction_results.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReviewStatus.PENDING.value,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=ReviewPriority.MEDIUM.value,
    )
    assigned_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Working copy of the candidate after human corrections (M4 candidate untouched).
    reviewed_candidate: Mapped[dict[str, Any] | None] = mapped_column(
        JsonDocument,
        nullable=True,
    )
    promoted_entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    promoted_entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    document: Mapped[Document] = relationship(back_populates="review_tasks")
    extraction_result: Mapped[DocumentExtractionResult] = relationship(
        back_populates="review_tasks",
    )
    decisions: Mapped[list[ReviewDecision]] = relationship(
        back_populates="review_task",
        cascade="all, delete-orphan",
        order_by="ReviewDecision.created_at",
    )


class ReviewDecision(Base):
    """Immutable audit record of a human review action."""

    __tablename__ = "review_decisions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    review_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("review_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ReviewAction.APPROVE.value,
    )
    field_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_value: Mapped[Any | None] = mapped_column(JsonDocument, nullable=True)
    corrected_value: Mapped[Any | None] = mapped_column(JsonDocument, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_ref: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    review_task: Mapped[ReviewTask] = relationship(back_populates="decisions")


class PolicyDocument(Base):
    """Logical policy identity in the M7 knowledge base (not procurement data)."""

    __tablename__ = "policy_documents"
    __table_args__ = (
        UniqueConstraint("name", name="uq_policy_documents_name"),
        Index("ix_policy_documents_name", "name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    versions: Mapped[list[PolicyVersion]] = relationship(
        back_populates="policy_document",
        cascade="all, delete-orphan",
        order_by="PolicyVersion.created_at",
    )


class PolicyVersion(Base):
    """A specific version of a policy document with provenance metadata."""

    __tablename__ = "policy_versions"
    __table_args__ = (
        UniqueConstraint(
            "policy_document_id",
            "version_label",
            name="uq_policy_versions_document_version_label",
        ),
        Index("ix_policy_versions_status", "status"),
        Index("ix_policy_versions_effective_from", "effective_from"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    policy_document_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("policy_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=PolicyVersionStatus.DRAFT.value,
    )
    effective_from: Mapped[date] = mapped_column(Date, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
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

    policy_document: Mapped[PolicyDocument] = relationship(back_populates="versions")
    chunks: Mapped[list[PolicyChunk]] = relationship(
        back_populates="policy_version",
        cascade="all, delete-orphan",
        order_by="PolicyChunk.chunk_index",
    )


class PolicyChunk(Base):
    """Retrievable policy section with citation provenance.

    ``content`` is the source of truth. ``embedding`` is derived data and may be
    null until M7.3 embedding runs; staleness is detected via
    ``embedding_content_hash`` / ``embedding_model``.
    """

    __tablename__ = "policy_chunks"
    __table_args__ = (
        UniqueConstraint(
            "policy_version_id",
            "chunk_index",
            name="uq_policy_chunks_version_chunk_index",
        ),
        Index("ix_policy_chunks_section_id", "section_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    policy_version_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("policy_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    section_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    section_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_filename: Mapped[str | None] = mapped_column(String(512), nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # M7.3 derived embedding (nullable until embedded).
    embedding: Mapped[list[float] | None] = mapped_column(
        PolicyEmbeddingVector,
        nullable=True,
    )
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    policy_version: Mapped[PolicyVersion] = relationship(back_populates="chunks")


class PolicyGroundingResult(Base):
    """AI-derived policy explanation audit row (M7.4).

    Never authoritative financial truth. Does not overwrite reconciliation exceptions.
    """

    __tablename__ = "policy_grounding_results"
    __table_args__ = (
        Index("ix_policy_grounding_results_exception_id", "reconciliation_exception_id"),
        Index("ix_policy_grounding_results_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reconciliation_exception_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("reconciliation_exceptions.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    policy_support: Mapped[str] = mapped_column(Text, nullable=False, default="")
    limitations: Mapped[str] = mapped_column(Text, nullable=False, default="")
    citations: Mapped[list[Any]] = mapped_column(JsonDocument, nullable=False, default=list)
    retrieved_chunk_ids: Mapped[list[Any]] = mapped_column(
        JsonDocument, nullable=False, default=list
    )
    retrieval_query: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_metadata: Mapped[dict[str, Any]] = mapped_column(
        JsonDocument, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ResolutionPlan(Base):
    """Agent-proposed resolution plan for a reconciliation exception (M8).

    Plans never mutate financial records. They only orchestrate validated
    workflow actions subject to guardrails and human approval.
    """

    __tablename__ = "resolution_plans"
    __table_args__ = (
        Index("ix_resolution_plans_exception_id", "reconciliation_exception_id"),
        Index("ix_resolution_plans_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    reconciliation_exception_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        # RESTRICT: deleting an exception must not silently destroy the audit trail.
        ForeignKey("reconciliation_exceptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ResolutionPlanStatus.PROPOSED.value,
    )
    reasoning_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    policy_grounding_result_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("policy_grounding_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    proposed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
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

    proposed_actions: Mapped[list[ProposedAction]] = relationship(
        back_populates="resolution_plan",
        cascade="all, delete-orphan",
        order_by="ProposedAction.action_order",
    )


class ProposedAction(Base):
    """One concrete workflow action within a ResolutionPlan."""

    __tablename__ = "proposed_actions"
    __table_args__ = (
        UniqueConstraint(
            "resolution_plan_id",
            "action_order",
            name="uq_proposed_actions_plan_order",
        ),
        Index("ix_proposed_actions_plan_id", "resolution_plan_id"),
        Index("ix_proposed_actions_status", "status"),
        Index("ix_proposed_actions_action_type", "action_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    resolution_plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("resolution_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    action_order: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JsonDocument, nullable=False, default=dict)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ProposedActionStatus.PENDING.value,
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

    resolution_plan: Mapped[ResolutionPlan] = relationship(back_populates="proposed_actions")
    approvals: Mapped[list[ActionApproval]] = relationship(
        back_populates="proposed_action",
        cascade="all, delete-orphan",
        order_by="ActionApproval.created_at",
    )
    executions: Mapped[list[ActionExecution]] = relationship(
        back_populates="proposed_action",
        cascade="all, delete-orphan",
        order_by="ActionExecution.started_at",
    )


class ActionApproval(Base):
    """Immutable human authorization decision for a ProposedAction.

    Historical decisions are never overwritten — append a new row instead.
    """

    __tablename__ = "action_approvals"
    __table_args__ = (Index("ix_action_approvals_proposed_action_id", "proposed_action_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    proposed_action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("proposed_actions.id", ondelete="CASCADE"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    proposed_action: Mapped[ProposedAction] = relationship(back_populates="approvals")


class ActionExecution(Base):
    """Execution attempt/result for a ProposedAction.

    ``idempotency_key`` is unique so retries cannot create duplicate executions.
    """

    __tablename__ = "action_executions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_action_executions_idempotency_key"),
        Index("ix_action_executions_proposed_action_id", "proposed_action_id"),
        Index("ix_action_executions_status", "execution_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    proposed_action_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("proposed_actions.id", ondelete="CASCADE"),
        nullable=False,
    )
    execution_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=ExecutionStatus.PENDING.value,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JsonDocument, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    proposed_action: Mapped[ProposedAction] = relationship(back_populates="executions")


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
    "Document",
    "DocumentExtractionResult",
    "LlmExtractionResult",
    "ReviewTask",
    "ReviewDecision",
    "PolicyDocument",
    "PolicyVersion",
    "PolicyChunk",
    "PolicyGroundingResult",
    "ResolutionPlan",
    "ProposedAction",
    "ActionApproval",
    "ActionExecution",
    "ActionType",
    "ApprovalDecision",
    "DocumentStatus",
    "DocumentType",
    "ExceptionSeverity",
    "ExceptionStatus",
    "ExceptionType",
    "ExecutionStatus",
    "GoodsReceiptStatus",
    "InvoiceStatus",
    "PurchaseOrderStatus",
    "PolicyVersionStatus",
    "ProposedActionStatus",
    "ResolutionPlanStatus",
    "ReviewAction",
    "ReviewPriority",
    "ReviewStatus",
]
