"""Read-only executive dashboard contracts (M10.2)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CountMap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int = Field(ge=0)
    counts: dict[str, int]


class DashboardExceptionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    exception_type: str
    severity: str
    status: str
    message: str
    invoice_number: str | None = None
    po_number: str | None = None
    grn_number: str | None = None
    created_at: datetime


class DashboardRiskProfileItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    entity_type: str
    entity_id: UUID
    score: int = Field(ge=0, le=100)
    risk_band: str
    score_version: str
    as_of: str
    signal_count: int = Field(ge=0)
    calculated_at: datetime


class DashboardReviewItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    status: str
    priority: str
    reason: str | None = None
    document_filename: str
    created_at: datetime


class DashboardActivityItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    record_id: UUID
    occurred_at: datetime
    title: str
    detail: str


class DashboardSummaryResponse(BaseModel):
    """Aggregates of persisted records. Not a recalculation of financial truth."""

    model_config = ConfigDict(extra="forbid")

    documents: CountMap
    reconciliation_exceptions: CountMap
    exception_severity: CountMap
    open_exception_count: int = Field(ge=0)
    in_review_exception_count: int = Field(ge=0)
    open_exceptions: list[DashboardExceptionItem]
    anomaly_signals: CountMap
    risk_profiles: CountMap
    high_or_critical_risk_count: int = Field(ge=0)
    latest_risk_profiles: list[DashboardRiskProfileItem]
    review_tasks: CountMap
    pending_review_count: int = Field(ge=0)
    pending_reviews: list[DashboardReviewItem]
    recent_activity: list[DashboardActivityItem]
    reconciliation_note: str
    risk_note: str
    review_note: str
    document_note: str
