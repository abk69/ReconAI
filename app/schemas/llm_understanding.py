"""API schemas for LLM-assisted understanding (M6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import ApplicationQuality, LlmInvocationStatus


class LlmUnderstandingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: UUID
    m4_extraction_result_id: UUID | None = None
    provider: str
    model: str
    prompt_version: str
    invocation_status: LlmInvocationStatus
    application_quality: ApplicationQuality | None = None
    quality_reasons: list[str] = Field(default_factory=list)
    gate_reasons: list[str] = Field(default_factory=list)
    candidate: dict[str, Any] | None = None
    evidence: list[Any] = Field(default_factory=list)
    validation: dict[str, Any] = Field(default_factory=dict)
    comparison: dict[str, Any] | None = None
    evidence_check: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    message: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    document_status: str | None = None
    created_at: datetime
