"""API schemas for M9.3 transparent risk scoring."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.risk.enums import RiskBand, RiskEntityType


class RiskProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    entity_type: RiskEntityType
    entity_id: UUID
    score: int = Field(ge=0, le=100)
    risk_band: RiskBand
    score_version: str
    as_of: date
    calculated_at: datetime
    signal_count: int
    breakdown: dict[str, Any]
    fingerprint: str
    created_at: datetime
    note: str = (
        "Risk score is a deterministic aggregation of observed anomaly signals. "
        "It is not a probability of fraud and is not a fraud determination."
    )
