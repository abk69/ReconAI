"""Shared API response schemas."""

from pydantic import BaseModel, ConfigDict


class HealthResponse(BaseModel):
    """Liveness probe response."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
