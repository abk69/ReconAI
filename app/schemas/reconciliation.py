"""API schemas for reconciliation endpoints."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ExceptionSeverity, ExceptionType, ReconciliationStatus


class ReconciliationRunRequest(BaseModel):
    """Request body for POST /reconciliation/run."""

    model_config = ConfigDict(extra="forbid")

    purchase_order_id: UUID | None = None
    invoice_id: UUID | None = None
    quantity_tolerance: Decimal | None = Field(default=None, ge=Decimal("0"))
    price_tolerance_percent: Decimal | None = Field(default=None, ge=Decimal("0"))
    tax_rate_tolerance_percent: Decimal | None = Field(default=None, ge=Decimal("0"))
    persist: bool = True


class ExceptionResponse(BaseModel):
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


class ReconciliationSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exception_count_by_type: dict[str, int] = Field(default_factory=dict)
    po_line_count: int = 0
    grn_count: int = 0
    invoice_line_count: int = 0
    total_ordered_quantity: Decimal = Decimal("0")
    total_received_quantity: Decimal = Decimal("0")
    total_invoiced_quantity: Decimal = Decimal("0")


class ReconciliationRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReconciliationStatus
    exception_count: int
    exceptions: list[ExceptionResponse]
    summary: ReconciliationSummaryResponse
    document_ids: list[UUID]
    purchase_order_id: UUID | None = None
    invoice_id: UUID | None = None
    goods_receipt_ids: list[UUID] = Field(default_factory=list)
