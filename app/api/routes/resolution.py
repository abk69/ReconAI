"""Agentic resolution plan inspection and approval APIs (M8).

Approval/reject endpoints record human decisions only — they never execute.
M8.4 strengthens the human authorization boundary; execution remains separate.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
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
    ActionDecisionResponse,
    ActionExecuteRequest,
    ActionExecuteResponse,
    ActionExecutionListResponse,
    ActionExecutionResponse,
    ActionRejectRequest,
    ProposedActionListResponse,
    ProposedActionResponse,
    ResolutionAuditEventResponse,
    ResolutionAuditTrailResponse,
    ResolutionPlanResponse,
)
from app.services.resolution_audit_service import (
    ResolutionAuditNotFoundError,
    ResolutionAuditService,
)
from app.services.resolution_execution_service import (
    ResolutionExecutionConflictError,
    ResolutionExecutionNotFoundError,
    ResolutionExecutionService,
    ResolutionExecutionValidationError,
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
        approved_parameters_hash=getattr(action, "approved_parameters_hash", None),
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


def _approval_row_response(row: ActionApproval) -> ActionApprovalResponse:
    return ActionApprovalResponse(
        id=row.id,
        proposed_action_id=row.proposed_action_id,
        decision=ApprovalDecision(row.decision),
        reviewer=row.reviewer,
        reason=row.reason,
        decided_at=row.decided_at,
        created_at=row.created_at,
        idempotency_key=getattr(row, "idempotency_key", None),
    )


def _decision_response(
    *,
    plan: ResolutionPlan,
    action: ProposedAction,
    approval: ActionApproval,
    reused_existing: bool = False,
) -> ActionDecisionResponse:
    return ActionDecisionResponse(
        plan_id=plan.id,
        action_id=action.id,
        action_type=ActionType(action.action_type),
        action_status=ProposedActionStatus(action.status),
        plan_status=ResolutionPlanStatus(plan.status),
        approval_id=approval.id,
        decision=ApprovalDecision(approval.decision),
        reviewer=approval.reviewer,
        comment=approval.reason,
        decided_at=approval.decided_at,
        reused_existing=reused_existing,
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
    response_model=ActionDecisionResponse,
)
def approve_resolution_action(
    plan_id: UUID,
    action_id: UUID,
    body: ActionApprovalRequest,
    session: DbSession,
) -> ActionDecisionResponse:
    """Record APPROVED — never executes the action."""
    service = ResolutionService(session)
    try:
        action_before = service.get_action(plan_id, action_id)
        prior_ids = {a.id for a in action_before.approvals}
        approval = service.approve_action(
            plan_id,
            action_id,
            reviewer=body.reviewer,
            comment=body.comment,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
        plan = service.get_plan(plan_id)
        action = service.get_action(plan_id, action_id)
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResolutionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ResolutionValidationError, InvalidResolutionTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _decision_response(
        plan=plan,
        action=action,
        approval=approval,
        reused_existing=approval.id in prior_ids,
    )


@router.post(
    "/{plan_id}/actions/{action_id}/reject",
    response_model=ActionDecisionResponse,
)
def reject_resolution_action(
    plan_id: UUID,
    action_id: UUID,
    body: ActionRejectRequest,
    session: DbSession,
) -> ActionDecisionResponse:
    """Record REJECTED — never executes the action."""
    service = ResolutionService(session)
    try:
        action_before = service.get_action(plan_id, action_id)
        prior_ids = {a.id for a in action_before.approvals}
        approval = service.reject_action(
            plan_id,
            action_id,
            reviewer=body.reviewer,
            comment=body.comment,
            reason=body.reason,
            idempotency_key=body.idempotency_key,
        )
        plan = service.get_plan(plan_id)
        action = service.get_action(plan_id, action_id)
    except ResolutionNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ResolutionConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (ResolutionValidationError, InvalidResolutionTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _decision_response(
        plan=plan,
        action=action,
        approval=approval,
        reused_existing=approval.id in prior_ids,
    )


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


@router.get("/{plan_id}/audit", response_model=ResolutionAuditTrailResponse)
def get_resolution_plan_audit(
    plan_id: UUID,
    session: DbSession,
) -> ResolutionAuditTrailResponse:
    """Return chronological append-only audit events for one plan."""
    service = ResolutionAuditService(session)
    try:
        events = service.get_plan_audit(plan_id)
    except ResolutionAuditNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    responses = [
        ResolutionAuditEventResponse(
            id=row.id,
            event_type=row.event_type,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            proposed_action_id=row.proposed_action_id,
            action_execution_id=row.action_execution_id,
            created_at=row.created_at,
            data=dict(row.event_data or {}),
        )
        for row in events
    ]
    return ResolutionAuditTrailResponse(
        plan_id=plan_id,
        events=responses,
        count=len(responses),
    )


@router.post(
    "/{plan_id}/actions/{action_id}/execute",
    response_model=ActionExecuteResponse,
)
def execute_resolution_action(
    plan_id: UUID,
    action_id: UUID,
    body: ActionExecuteRequest,
    session: DbSession,
) -> ActionExecuteResponse:
    """Execute an approved proposed action using stored parameters only.

    Never calls Gemini. Never accepts client overrides of type/parameters/status.
    """
    service = ResolutionService(session)
    executor = ResolutionExecutionService(session)
    prior = session.scalar(
        select(ActionExecution).where(ActionExecution.idempotency_key == body.idempotency_key)
    )
    prior_id = prior.id if prior is not None else None

    try:
        execution = executor.execute_action(
            plan_id,
            action_id,
            idempotency_key=body.idempotency_key,
        )
        plan = service.get_plan(plan_id)
        action = service.get_action(plan_id, action_id)
    except (
        ResolutionNotFoundError,
        ResolutionExecutionNotFoundError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (
        ResolutionConflictError,
        ResolutionExecutionConflictError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except (
        ResolutionValidationError,
        ResolutionExecutionValidationError,
        InvalidResolutionTransitionError,
    ) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    return ActionExecuteResponse(
        plan_id=plan.id,
        action_id=action.id,
        action_type=ActionType(action.action_type),
        execution_id=execution.id,
        execution_status=ExecutionStatus(execution.execution_status),
        action_status=ProposedActionStatus(action.status),
        plan_status=ResolutionPlanStatus(plan.status),
        idempotency_key=execution.idempotency_key,
        result=execution.result,
        error_code=execution.error_code,
        error_message=execution.error_message,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        reused_existing=prior_id is not None and execution.id == prior_id,
    )
