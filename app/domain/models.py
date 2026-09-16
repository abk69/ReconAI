"""Pydantic domain models for procurement documents and exceptions.

These models represent structured procurement data. Monetary amounts use
``Decimal`` to avoid floating-point rounding errors. The deterministic
reconciliation engine (not yet implemented) will treat these as facts;
the LLM/AI layer must not redefine them.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ExceptionSeverity, ExceptionType


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Vendor(BaseModel):
    """A supplier / vendor master record."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    name: str
    code: str | None = None
    tax_id: str | None = None


class PurchaseOrderLine(BaseModel):
    """A single line item on a purchase order."""

    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    sku: str
    description: str | None = None
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price: Decimal = Field(ge=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=3)


class PurchaseOrder(BaseModel):
    """A purchase order issued to a vendor."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    po_number: str
    vendor_id: UUID
    order_date: date
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines: list[PurchaseOrderLine] = Field(default_factory=list)


class GoodsReceiptLine(BaseModel):
    """A single line item on a goods receipt / GRN."""

    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    sku: str
    description: str | None = None
    quantity_received: Decimal = Field(gt=Decimal("0"))
    po_line_number: int | None = Field(default=None, ge=1)


class GoodsReceipt(BaseModel):
    """A goods receipt note (GRN) confirming delivery against a PO."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    grn_number: str
    po_id: UUID
    vendor_id: UUID
    receipt_date: date
    lines: list[GoodsReceiptLine] = Field(default_factory=list)


class InvoiceLine(BaseModel):
    """A single line item on a vendor invoice."""

    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    sku: str
    description: str | None = None
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price: Decimal = Field(ge=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    currency: str = Field(default="USD", min_length=3, max_length=3)


class Invoice(BaseModel):
    """A vendor invoice submitted for payment."""

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    invoice_number: str
    vendor_id: UUID
    po_id: UUID | None = None
    invoice_date: date
    currency: str = Field(default="USD", min_length=3, max_length=3)
    lines: list[InvoiceLine] = Field(default_factory=list)
    total_amount: Decimal = Field(ge=Decimal("0"))
    tax_total: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class ReconciliationException(BaseModel):
    """An exception detected during deterministic reconciliation.

    ``evidence`` holds structured facts that justify the exception so
    auditors and later AI explanation layers can reference the same
    ground truth established by the reconciliation engine.
    """

    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    type: ExceptionType
    severity: ExceptionSeverity
    message: str
    source_document_ids: list[UUID] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=_utc_now)
