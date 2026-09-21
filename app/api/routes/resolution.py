"""Agentic resolution plan inspection and approval APIs (M8.1).

Approval/reject endpoints record human decisions only — they never execute.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.models import ActionApproval, ActionExecution, ProposedAction, ResolutionPlan
from app.db.session import get_db
from app.domain.enums import (
    ActionType,
    ApprovalDecision,
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.resolution.transitions import InvalidResolutionTransitionError
from app.schemas.resolution import (
    ActionApprovalRequest,
    ActionApprovalResponse,
    ActionExecuteRequest,
    ActionExecutionListResponse,
    ActionExecutionResponse,
    ActionRejectRequest,
    ProposedActionListResponse,
    ProposedActionResponse,
    ResolutionPlanResponse,
)
from app.services.resolution_service import (
    ResolutionConflictError,
    ResolutionNotFoundError,
    ResolutionService,
    ResolutionValidationError,
)

router = APIRouter(prefix="/resolution-plans", tags=["resolution"])
DbSession = Annotated[Session, Depends(get_db)]


def _action_response(action: ProposedAction) -> ProposedActionResponse:
    return ProposedActionResponse(
        id=action.id,
        resolution_plan_id=action.resolution_plan_id,
        action_type=ActionType(action.action_type),
        action_order=action.action_order,
        parameters=dict(action.parameters or {}),
        rationale=action.rationale,
        requires_approval=action.requires_approval,
        status=ProposedActionStatus(action.status),
        created_at=action.created_at,
        updated_at=action.updated_at,
    )


def _plan_response(plan: ResolutionPlan) -> ResolutionPlanResponse:
    actions = sorted(plan.proposed_actions or [], key=lambda a: a.action_order)
    return ResolutionPlanResponse(
        id=plan.id,
        reconciliation_exception_id=plan.reconciliation_exception_id,
        status=ResolutionPlanStatus(plan.status),
        reasoning_summary=plan.reasoning_summary,
        policy_grounding_result_id=plan.policy_grounding_result_id,
        proposed_by=plan.proposed_by,
        planning_key=getattr(plan, "planning_key", None),
        planner_model=getattr(plan, "planner_model", None),
        prompt_version=getattr(plan, "prompt_version", None),
        limitations=getattr(plan, "limitations", "") or "",
        planning_latency_ms=getattr(plan, "planning_latency_ms", None),
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        actions=[_action_response(a) for a in actions],
    )


def _approval_response(row: ActionApproval) -> ActionApprovalResponse:
    return ActionApprovalResponse(
        id=row.id,
        proposed_action_id=row.proposed_action_id,
        decision=ApprovalDecision(row.decision),
        reviewer=row.reviewer,
        reason=row.reason,
        decided_at=row.decided_at,
        created_at=row.created_at,
    )


def _execution_response(row: ActionExecution) -> ActionExecutionResponse:
    return ActionExecutionResponse(
        id=row.id,
        proposed_action_id=row.proposed_action_id,
        execution_status=ExecutionStatus(row.execution_status),
        idempotency_key=row.idempotency_key,
        started_at=row.started_at,
        completed_at=row.completed_at,
        result=row.result,
        error_code=row.error_code,
        error_message=row.error_message,
        created_at=row.created_at,
    )


@router.get("/{plan_id}", response_model=ResolutionPlanResponse)
def get_resolution_plan(plan_id: UUID, session: DbSession) -> ResolutionPlanResponse:
    service = ResolutionService(session)
    try:
        return _plan_response(service.get_plan(plan_id))
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/{plan_id}/actions", response_model=ProposedActionListResponse)
def list_resolution_actions(
    plan_id: UUID,
    session: DbSession,
) -> ProposedActionListResponse:
    service = ResolutionService(session)
    try:
        items = service.list_actions(plan_id)
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    responses = [_action_response(a) for a in items]
    return ProposedActionListResponse(items=responses, count=len(responses))


@router.post(
    "/{plan_id}/actions/{action_id}/approve",
    response_model=ActionApprovalResponse,
)
def approve_resolution_action(
    plan_id: UUID,
    action_id: UUID,
    body: ActionApprovalRequest,
    session: DbSession,
) -> ActionApprovalResponse:
    service = ResolutionService(session)
    try:
        approval = service.approve_action(
            plan_id,
            action_id,
            reviewer=body.reviewer,
            reason=body.reason,
        )
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ResolutionValidationError, InvalidResolutionTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _approval_response(approval)


@router.post(
    "/{plan_id}/actions/{action_id}/reject",
    response_model=ActionApprovalResponse,
)
def reject_resolution_action(
    plan_id: UUID,
    action_id: UUID,
    body: ActionRejectRequest,
    session: DbSession,
) -> ActionApprovalResponse:
    service = ResolutionService(session)
    try:
        approval = service.reject_action(
            plan_id,
            action_id,
            reviewer=body.reviewer,
            reason=body.reason,
        )
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ResolutionValidationError, InvalidResolutionTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _approval_response(approval)


@router.get("/{plan_id}/executions", response_model=ActionExecutionListResponse)
def list_resolution_executions(
    plan_id: UUID,
    session: DbSession,
) -> ActionExecutionListResponse:
    service = ResolutionService(session)
    try:
        items = service.list_executions(plan_id)
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    responses = [_execution_response(e) for e in items]
    return ActionExecutionListResponse(items=responses, count=len(responses))


@router.post(
    "/{plan_id}/actions/{action_id}/execute",
    response_model=ActionExecutionResponse,
)
def execute_resolution_action(
    plan_id: UUID,
    action_id: UUID,
    body: ActionExecuteRequest,
    session: DbSession,
) -> ActionExecutionResponse:
    """Execute an approved proposed action using stored parameters only."""
    service = ResolutionService(session)
    try:
        execution = service.execute_action(
            plan_id,
            action_id,
            idempotency_key=body.idempotency_key,
        )
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResolutionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ResolutionValidationError, InvalidResolutionTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _execution_response(execution)
