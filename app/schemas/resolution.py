"""API schemas for agentic resolution plans (M8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    ActionType,
    ApprovalDecision,
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionPlanStatus,
)


class ActionApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=255)
    reason: str | None = None


class ActionRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=255)
    reason: str | None = None


class ActionExecuteRequest(BaseModel):
    """Execute a proposed action. Stored parameters are authoritative."""

    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=1, max_length=128)


class ProposedActionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    resolution_plan_id: UUID
    action_type: ActionType
    action_order: int
    parameters: dict[str, Any]
    rationale: str
    requires_approval: bool
    status: ProposedActionStatus
    created_at: datetime
    updated_at: datetime


class ActionApprovalResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    proposed_action_id: UUID
    decision: ApprovalDecision
    reviewer: str
    reason: str | None = None
    decided_at: datetime
    created_at: datetime


class ActionExecutionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    proposed_action_id: UUID
    execution_status: ExecutionStatus
    idempotency_key: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime


class ResolutionPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    reconciliation_exception_id: UUID
    status: ResolutionPlanStatus
    reasoning_summary: str
    policy_grounding_result_id: UUID | None = None
    proposed_by: str | None = None
    created_at: datetime
    updated_at: datetime
    actions: list[ProposedActionResponse] = Field(default_factory=list)


class ProposedActionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProposedActionResponse]
    count: int


class ActionExecutionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActionExecutionResponse]
    count: int
