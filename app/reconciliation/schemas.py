"""Pure data structures for the deterministic reconciliation engine.

These schemas are independent of FastAPI and SQLAlchemy so the engine can be
unit-tested with plain fixtures.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ExceptionSeverity, ExceptionType, ReconciliationStatus


class ReconciliationConfig(BaseModel):
    """Configurable numeric tolerances for reconciliation rules."""

    model_config = ConfigDict(extra="forbid")

    quantity_tolerance: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    price_tolerance_percent: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    tax_rate_tolerance_percent: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class EnginePurchaseOrderLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    line_number: int
    description: str | None = None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal = Decimal("0")


class EnginePurchaseOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    po_number: str
    vendor_id: UUID
    order_date: date
    currency: str = "USD"
    lines: list[EnginePurchaseOrderLine] = Field(default_factory=list)


class EngineGoodsReceiptLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    line_number: int
    received_quantity: Decimal
    purchase_order_line_id: UUID | None = None


class EngineGoodsReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    grn_number: str
    purchase_order_id: UUID
    receipt_date: date
    lines: list[EngineGoodsReceiptLine] = Field(default_factory=list)


class EngineInvoiceLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    line_number: int
    description: str | None = None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal = Decimal("0")
    purchase_order_line_id: UUID | None = None


class EngineInvoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    invoice_number: str
    vendor_id: UUID
    purchase_order_id: UUID | None = None
    invoice_date: date
    currency: str = "USD"
    lines: list[EngineInvoiceLine] = Field(default_factory=list)


class DuplicateInvoiceCandidate(BaseModel):
    """Another invoice that may share vendor + normalized number."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    vendor_id: UUID
    invoice_number: str


class ReconciliationInput(BaseModel):
    """Documents supplied to a single reconciliation run."""

    model_config = ConfigDict(extra="forbid")

    purchase_order: EnginePurchaseOrder | None = None
    goods_receipts: list[EngineGoodsReceipt] = Field(default_factory=list)
    invoice: EngineInvoice | None = None
    duplicate_candidates: list[DuplicateInvoiceCandidate] = Field(default_factory=list)
    config: ReconciliationConfig = Field(default_factory=ReconciliationConfig)


class ExceptionDraft(BaseModel):
    """An exception produced by the engine before persistence."""

    model_config = ConfigDict(extra="forbid")

    exception_type: ExceptionType
    severity: ExceptionSeverity
    message: str
    fingerprint: str
    purchase_order_id: UUID | None = None
    goods_receipt_id: UUID | None = None
    invoice_id: UUID | None = None
    source_document_ids: list[UUID] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ReconciliationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exception_count_by_type: dict[str, int] = Field(default_factory=dict)
    po_line_count: int = 0
    grn_count: int = 0
    invoice_line_count: int = 0
    total_ordered_quantity: Decimal = Decimal("0")
    total_received_quantity: Decimal = Decimal("0")
    total_invoiced_quantity: Decimal = Decimal("0")


class ReconciliationResult(BaseModel):
    """Structured outcome of a deterministic reconciliation run."""

    model_config = ConfigDict(extra="forbid")

    status: ReconciliationStatus
    exception_count: int
    exceptions: list[ExceptionDraft] = Field(default_factory=list)
    summary: ReconciliationSummary = Field(default_factory=ReconciliationSummary)
    document_ids: list[UUID] = Field(default_factory=list)
    purchase_order_id: UUID | None = None
    invoice_id: UUID | None = None
    goods_receipt_ids: list[UUID] = Field(default_factory=list)
