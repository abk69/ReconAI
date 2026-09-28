"""Shared API response schemas."""

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
