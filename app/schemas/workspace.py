"""Read models for procurement workspace lists. Amounts are stored values."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PageMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class PurchaseOrderListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    po_number: str
    vendor_id: UUID
    vendor_name: str
    order_date: date
    currency: str
    status: str
    line_count: int = Field(ge=0)
    created_at: datetime


class PurchaseOrderListResponse(PageMeta):
    items: list[PurchaseOrderListItem]


class GoodsReceiptListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    grn_number: str
    purchase_order_id: UUID
    po_number: str
    receipt_date: date
    status: str
    line_count: int = Field(ge=0)
    created_at: datetime


class GoodsReceiptListResponse(PageMeta):
    items: list[GoodsReceiptListItem]


class InvoiceListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    invoice_number: str
    vendor_id: UUID
    vendor_name: str
    purchase_order_id: UUID | None
    po_number: str | None
    invoice_date: date
    currency: str
    status: str
    total_amount: Decimal
    line_count: int = Field(ge=0)
    created_at: datetime


class InvoiceListResponse(PageMeta):
    items: list[InvoiceListItem]


class ReconciliationExceptionListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    exception_type: str
    severity: str
    status: str
    message: str
    invoice_id: UUID | None
    invoice_number: str | None
    purchase_order_id: UUID | None
    po_number: str | None
    goods_receipt_id: UUID | None
    grn_number: str | None
    created_at: datetime


class ReconciliationExceptionListResponse(PageMeta):
    items: list[ReconciliationExceptionListItem]
    counts_by_status: dict[str, int]


class ReconciliationExceptionDetail(ReconciliationExceptionListItem):
    source_document_ids: list[Any]
    evidence: dict[str, Any]
    resolved_at: datetime | None


class PolicyGroundingRead(BaseModel):
    """Persisted AI policy explanation. Not a reconciliation fact."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    reconciliation_exception_id: UUID
    status: str
    conclusion: str
    explanation: str
    policy_support: str
    limitations: str
    citations: list[Any]
    created_at: datetime
    model: str | None = None


class PolicyGroundingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PolicyGroundingRead]
    count: int
