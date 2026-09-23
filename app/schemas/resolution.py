"""API schemas for agentic resolution plans (M8)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import (
    ActionType,
    ApprovalDecision,
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.resolution.reviewer import InvalidReviewerError, validate_reviewer


class ActionApprovalRequest(BaseModel):
    """Approve a proposed action. Never executes.

    ``comment`` is preferred; ``reason`` is accepted as a synonym for M8.1 clients.
    Production auth will supply ``reviewer``; for now it is application-provided.
    """

    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=255)
    comment: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("reviewer")
    @classmethod
    def _check_reviewer(cls, value: str) -> str:
        try:
            return validate_reviewer(value)
        except InvalidReviewerError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _normalize_comment(self) -> ActionApprovalRequest:
        if self.comment is None and self.reason is not None:
            self.comment = self.reason
        return self


class ActionRejectRequest(BaseModel):
    """Reject a proposed action. Never executes."""

    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=255)
    comment: str | None = Field(default=None, max_length=4000)
    reason: str | None = Field(default=None, max_length=4000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("reviewer")
    @classmethod
    def _check_reviewer(cls, value: str) -> str:
        try:
            return validate_reviewer(value)
        except InvalidReviewerError as exc:
            raise ValueError(str(exc)) from exc

    @model_validator(mode="after")
    def _normalize_comment(self) -> ActionRejectRequest:
        if self.comment is None and self.reason is not None:
            self.comment = self.reason
        return self


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
    approved_parameters_hash: str | None = None
    created_at: datetime
    updated_at: datetime


class ActionApprovalResponse(BaseModel):
    """Legacy approval-row shape (still used for audit listing)."""

    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    proposed_action_id: UUID
    decision: ApprovalDecision
    reviewer: str
    reason: str | None = None
    decided_at: datetime
    created_at: datetime
    idempotency_key: str | None = None


class ActionDecisionResponse(BaseModel):
    """M8.4 approval/rejection API response — decision only, never execution."""

    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    action_id: UUID
    action_type: ActionType
    action_status: ProposedActionStatus
    plan_status: ResolutionPlanStatus
    approval_id: UUID
    decision: ApprovalDecision
    reviewer: str
    comment: str | None = None
    decided_at: datetime
    reused_existing: bool = False


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


class ActionExecuteResponse(BaseModel):
    """M8.5 execute API response — structured result, never LLM-driven."""

    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    action_id: UUID
    action_type: ActionType
    execution_id: UUID
    execution_status: ExecutionStatus
    action_status: ProposedActionStatus
    plan_status: ResolutionPlanStatus
    idempotency_key: str
    result: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    reused_existing: bool = False


class ResolutionPlanResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    reconciliation_exception_id: UUID
    status: ResolutionPlanStatus
    reasoning_summary: str
    policy_grounding_result_id: UUID | None = None
    proposed_by: str | None = None
    planning_key: str | None = None
    planner_model: str | None = None
    prompt_version: str | None = None
    limitations: str = ""
    planning_latency_ms: int | None = None
    created_at: datetime
    updated_at: datetime
    actions: list[ProposedActionResponse] = Field(default_factory=list)


class ProposedActionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ProposedActionResponse]
    count: int


class ResolutionPlanListItem(BaseModel):
    """List row. Reasoning is an AI proposal, not a financial decision."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    reconciliation_exception_id: UUID
    status: str
    reasoning_summary: str
    proposed_by: str | None = None
    planner_model: str | None = None
    created_at: datetime
    action_count: int = Field(ge=0)
    exception_type: str | None = None
    exception_message: str | None = None


class ResolutionPlanListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ResolutionPlanListItem]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class ActionApprovalListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActionApprovalResponse]
    count: int


class ActionExecutionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ActionExecutionResponse]
    count: int


class ResolutionAuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    event_type: str
    actor_type: str
    actor_id: str | None = None
    proposed_action_id: UUID | None = None
    action_execution_id: UUID | None = None
    created_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)


class ResolutionAuditTrailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: UUID
    events: list[ResolutionAuditEventResponse] = Field(default_factory=list)
    count: int
