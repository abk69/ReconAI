"""API schemas for M9.1 anomaly detection."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.anomaly.enums import AnomalySeverity, AnomalyType


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
