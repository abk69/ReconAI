"""API schemas for human review queue (M5)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DocumentType, ReviewAction, ReviewPriority, ReviewStatus


class FieldCorrectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str = Field(min_length=1, max_length=255)
    corrected_value: Any
    reason: str | None = None
    evidence_ref: str | None = Field(default=None, max_length=512)


class ReviewApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str | None = Field(default=None, max_length=255)
    reason: str | None = None


class ReviewCorrectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str | None = Field(default=None, max_length=255)
    reason: str | None = None
    corrections: list[FieldCorrectionRequest] = Field(min_length=1)


class ReviewRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str | None = Field(default=None, max_length=255)
    reason: str | None = None


class ReviewDecisionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    action: ReviewAction
    field_path: str | None = None
    original_value: Any = None
    corrected_value: Any = None
    reason: str | None = None
    reviewer: str | None = None
    evidence_ref: str | None = None
    created_at: datetime


class ReviewTaskResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    document_id: UUID
    extraction_result_id: UUID
    status: ReviewStatus
    reason: str | None = None
    priority: ReviewPriority
    assigned_to: str | None = None
    document_type: DocumentType | None = None
    detected_type: DocumentType | None = None
    document_status: str | None = None
    original_filename: str | None = None
    candidate_summary: dict[str, Any] | None = None
    reviewed_candidate: dict[str, Any] | None = None
    original_candidate: dict[str, Any] | None = None
    evidence: list[Any] = Field(default_factory=list)
    decisions: list[ReviewDecisionResponse] = Field(default_factory=list)
    promoted_entity_type: str | None = None
    promoted_entity_id: UUID | None = None
    promoted_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class ReviewTaskListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ReviewTaskResponse]
    count: int
    total: int = 0
    limit: int | None = None
    offset: int = 0


class PromoteResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_task_id: UUID
    status: ReviewStatus
    document_id: UUID
    document_status: str
    promoted_entity_type: str | None = None
    promoted_entity_id: UUID | None = None
    promoted_at: datetime | None = None
