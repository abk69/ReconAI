"""API schemas for M9 anomaly detection, scans, and analytics."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.anomaly.enums import (
    AnomalyScanStatus,
    AnomalyScanType,
    AnomalySeverity,
    AnomalyTrendPeriod,
    AnomalyType,
)


class AnomalySignalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    anomaly_type: AnomalyType
    severity: AnomalySeverity
    score: Decimal
    vendor_id: UUID | None = None
    purchase_order_id: UUID | None = None
    invoice_id: UUID | None = None
    grn_id: UUID | None = None
    title: str
    explanation: str
    evidence: dict[str, Any]
    fingerprint: str
    detected_at: datetime
    created_at: datetime


class AnomalyDetectResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[AnomalySignalResponse]
    created_or_reused_count: int = Field(ge=0)


class AnomalyPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AnomalySignalResponse]
    next_cursor: str | None = None
    limit: int


class AnomalyScanCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_type: AnomalyScanType
    scan_key: str | None = Field(default=None, max_length=128)


class AnomalyScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    scan_type: AnomalyScanType
    status: AnomalyScanStatus
    scan_key: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_cursor: str | None = None
    processed_count: int
    anomaly_count: int
    error_count: int
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AnomalyScanCreateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scan_id: UUID
    status: AnomalyScanStatus
    reused_existing: bool = False


class RiskSignalSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_count: int
    medium_count: int
    high_count: int
    critical_count: int
    open_signal_count: int
    affected_vendor_count: int
    affected_invoice_count: int


class AnomalySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_signals: int
    counts_by_type: dict[str, int]
    counts_by_severity: dict[str, int]
    counts_by_date: dict[str, int]
    unique_affected_vendors: int
    unique_affected_invoices: int
    unique_affected_pos: int
    risk_signal_summary: RiskSignalSummary


class VendorAnomalySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id: UUID
    profile_kind: str = "anomaly_profile"
    total_anomalies: int
    anomalies_by_type: dict[str, int]
    anomalies_by_severity: dict[str, int]
    recent_anomaly_count: int
    recent_window_days: int
    affected_invoice_count: int
    affected_po_count: int
    repeated_mismatch_rate: str | None = None
    risk_signal_summary: RiskSignalSummary


class AnomalyTrendPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str
    count: int
    high_or_critical: int


class AnomalyTrendsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: AnomalyTrendPeriod
    points: list[AnomalyTrendPoint]
