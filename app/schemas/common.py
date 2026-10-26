"""Shared API response schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Liveness probe response. Does not check the database."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str


class ReadinessResponse(BaseModel):
    """Readiness probe response. Success means the database answered."""

    model_config = ConfigDict(extra="forbid")

    status: str


class WorkerHealthResponse(BaseModel):
    """Worker poll health. A stopped worker is stale or unavailable, not healthy."""

    model_config = ConfigDict(extra="forbid")

    status: str
    last_poll_at: datetime | None = None
