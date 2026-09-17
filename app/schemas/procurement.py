"""API schemas for structured procurement intake."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import GoodsReceiptStatus, InvoiceStatus, PurchaseOrderStatus


class VendorCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    tax_id: str | None = Field(default=None, max_length=64)


class VendorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    tax_id: str | None
    created_at: datetime
    updated_at: datetime


class PurchaseOrderLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    description: str | None = None
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price: Decimal = Field(ge=Decimal("0"))
    tax_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))


class PurchaseOrderCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    po_number: str = Field(min_length=1, max_length=64)
    vendor_id: UUID
    order_date: date
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: PurchaseOrderStatus = PurchaseOrderStatus.OPEN
    lines: list[PurchaseOrderLineCreate] = Field(default_factory=list)


class PurchaseOrderLineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    line_number: int
    description: str | None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    created_at: datetime


class PurchaseOrderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    po_number: str
    vendor_id: UUID
    order_date: date
    currency: str
    status: PurchaseOrderStatus
    lines: list[PurchaseOrderLineResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class GoodsReceiptLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    received_quantity: Decimal = Field(gt=Decimal("0"))
    purchase_order_line_id: UUID | None = None


class GoodsReceiptCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grn_number: str = Field(min_length=1, max_length=64)
    purchase_order_id: UUID
    receipt_date: date
    status: GoodsReceiptStatus = GoodsReceiptStatus.POSTED
    lines: list[GoodsReceiptLineCreate] = Field(default_factory=list)


class GoodsReceiptLineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    line_number: int
    received_quantity: Decimal
    purchase_order_line_id: UUID | None
    created_at: datetime


class GoodsReceiptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    grn_number: str
    purchase_order_id: UUID
    receipt_date: date
    status: GoodsReceiptStatus
    lines: list[GoodsReceiptLineResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class InvoiceLineCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int = Field(ge=1)
    description: str | None = None
    quantity: Decimal = Field(gt=Decimal("0"))
    unit_price: Decimal = Field(ge=Decimal("0"))
    tax_rate: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    purchase_order_line_id: UUID | None = None


class InvoiceCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str = Field(min_length=1, max_length=64)
    vendor_id: UUID
    invoice_date: date
    currency: str = Field(default="USD", min_length=3, max_length=3)
    status: InvoiceStatus = InvoiceStatus.RECEIVED
    purchase_order_id: UUID | None = None
    subtotal: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    tax_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    total_amount: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    lines: list[InvoiceLineCreate] = Field(default_factory=list)


class InvoiceLineResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    line_number: int
    description: str | None
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    purchase_order_line_id: UUID | None
    created_at: datetime


class InvoiceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    invoice_number: str
    vendor_id: UUID
    purchase_order_id: UUID | None
    invoice_date: date
    currency: str
    status: InvoiceStatus
    subtotal: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    lines: list[InvoiceLineResponse] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
