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


class RiskProfileListItem(BaseModel):
    """Latest stored profile for one entity and score version."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    entity_type: RiskEntityType
    entity_id: UUID
    entity_label: str | None = None
    score: int = Field(ge=0, le=100)
    risk_band: RiskBand
    score_version: str
    as_of: date
    calculated_at: datetime
    signal_count: int


class RiskProfileListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[RiskProfileListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    counts_by_band: dict[str, int]


class RiskProfileHistoryResponse(BaseModel):
    """Stored profiles only. Does not calculate a missing point in time."""

    model_config = ConfigDict(extra="forbid")

    entity_type: RiskEntityType
    entity_id: UUID
    entity_label: str | None = None
    current: RiskProfileResponse | None = None
    history: list[RiskProfileResponse]
