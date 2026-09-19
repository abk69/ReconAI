"""Resolution plan service — propose, approve, and guardrailed execute actions.

Approval endpoints only record decisions; they do not silently execute.
Handlers create workflow records only — never financial mutations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ActionApproval,
    ActionExecution,
    PolicyGroundingResult,
    ProposedAction,
    ReconciliationException,
    ResolutionPlan,
)
from app.domain.enums import (
    ApprovalDecision,
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.resolution.context import ActionExecutionContext
from app.resolution.contracts import ActionRequest, parse_action_request
from app.resolution.guardrails import (
    GuardrailError,
    validate_action,
    validate_approval,
    validate_execution,
)
from app.resolution.registry import ActionRegistry, build_default_registry
from app.resolution.transitions import (
    InvalidResolutionTransitionError,
    assert_action_transition,
    assert_execution_transition,
    assert_plan_transition,
)


class ResolutionServiceError(Exception):
    """Base resolution service error."""


class ResolutionNotFoundError(ResolutionServiceError):
    """Plan or action not found."""


class ResolutionValidationError(ResolutionServiceError):
    """Invalid input or guardrail failure."""


class ResolutionConflictError(ResolutionServiceError):
    """Idempotency or uniqueness conflict."""


class ResolutionService:
    """Orchestrate resolution plans without mutating financial truth."""

    def __init__(
        self,
        session: Session,
        *,
        registry: ActionRegistry | None = None,
    ) -> None:
        self._session = session
        self._registry = registry or build_default_registry()

    @property
    def registry(self) -> ActionRegistry:
        return self._registry

    def create_plan(
        self,
        *,
        reconciliation_exception_id: UUID,
        reasoning_summary: str = "",
        proposed_by: str | None = None,
        policy_grounding_result_id: UUID | None = None,
        actions: list[ActionRequest | dict[str, Any]] | None = None,
        commit: bool = True,
    ) -> ResolutionPlan:
        """Persist a ResolutionPlan with ordered ProposedActions."""
        exc = self._session.get(ReconciliationException, reconciliation_exception_id)
        if exc is None:
            raise ResolutionNotFoundError(
                f"Reconciliation exception {reconciliation_exception_id} was not found."
            )

        if policy_grounding_result_id is not None:
            grounding = self._session.get(PolicyGroundingResult, policy_grounding_result_id)
            if grounding is None:
                raise ResolutionNotFoundError(
                    f"Policy grounding result {policy_grounding_result_id} was not found."
                )
            if grounding.reconciliation_exception_id != reconciliation_exception_id:
                raise ResolutionValidationError(
                    "policy_grounding_result_id does not belong to the given exception."
                )

        parsed_actions = [parse_action_request(a) for a in (actions or [])]
        for request in parsed_actions:
            if not self._registry.is_registered(request.action_type):
                raise ResolutionValidationError(
                    f"Unknown or unregistered action type: {request.action_type.value}."
                )

        requires_any_approval = False
        plan = ResolutionPlan(
            reconciliation_exception_id=reconciliation_exception_id,
            status=ResolutionPlanStatus.PROPOSED.value,
            reasoning_summary=reasoning_summary,
            policy_grounding_result_id=policy_grounding_result_id,
            proposed_by=proposed_by,
        )
        self._session.add(plan)
        self._session.flush()

        for order, request in enumerate(parsed_actions):
            handler = self._registry.get(request.action_type)
            requires_approval = (
                handler.requires_approval
                if request.requires_approval is None
                else request.requires_approval
            )
            if requires_approval:
                requires_any_approval = True
            action = ProposedAction(
                resolution_plan_id=plan.id,
                action_type=request.action_type.value,
                action_order=order,
                parameters=dict(request.parameters),
                rationale=request.rationale,
                requires_approval=requires_approval,
                status=ProposedActionStatus.PENDING.value,
            )
            self._session.add(action)

        if requires_any_approval:
            plan.status = ResolutionPlanStatus.APPROVAL_REQUIRED.value
        elif parsed_actions:
            plan.status = ResolutionPlanStatus.APPROVED.value

        if commit:
            self._session.commit()
            return self.get_plan(plan.id)
        self._session.flush()
        return plan

    def get_plan(self, plan_id: UUID) -> ResolutionPlan:
        plan = self._session.scalar(
            select(ResolutionPlan)
            .where(ResolutionPlan.id == plan_id)
            .options(selectinload(ResolutionPlan.proposed_actions))
        )
        if plan is None:
            raise ResolutionNotFoundError(f"Resolution plan {plan_id} was not found.")
        return plan

    def list_actions(self, plan_id: UUID) -> list[ProposedAction]:
        plan = self.get_plan(plan_id)
        return sorted(plan.proposed_actions, key=lambda a: a.action_order)

    def get_action(self, plan_id: UUID, action_id: UUID) -> ProposedAction:
        cached = self._session.get(ProposedAction, action_id)
        if cached is not None:
            self._session.expire(cached, ["approvals", "executions", "status"])

        action = self._session.scalar(
            select(ProposedAction)
            .where(
                ProposedAction.id == action_id,
                ProposedAction.resolution_plan_id == plan_id,
            )
            .options(
                selectinload(ProposedAction.approvals),
                selectinload(ProposedAction.executions),
            )
        )
        if action is None:
            raise ResolutionNotFoundError(
                f"Proposed action {action_id} was not found on plan {plan_id}."
            )
        return action

    def approve_action(
        self,
        plan_id: UUID,
        action_id: UUID,
        *,
        reviewer: str,
        reason: str | None = None,
        commit: bool = True,
    ) -> ActionApproval:
        """Record an APPROVED decision only — does not execute the action."""
        return self._record_decision(
            plan_id,
            action_id,
            decision=ApprovalDecision.APPROVED,
            reviewer=reviewer,
            reason=reason,
            commit=commit,
        )

    def reject_action(
        self,
        plan_id: UUID,
        action_id: UUID,
        *,
        reviewer: str,
        reason: str | None = None,
        commit: bool = True,
    ) -> ActionApproval:
        """Record a REJECTED decision only — does not execute the action."""
        return self._record_decision(
            plan_id,
            action_id,
            decision=ApprovalDecision.REJECTED,
            reviewer=reviewer,
            reason=reason,
            commit=commit,
        )

    def list_executions(self, plan_id: UUID) -> list[ActionExecution]:
        self.get_plan(plan_id)
        rows = self._session.scalars(
            select(ActionExecution)
            .join(ProposedAction)
            .where(ProposedAction.resolution_plan_id == plan_id)
            .order_by(ActionExecution.created_at)
        ).all()
        return list(rows)

    def execute_action(
        self,
        plan_id: UUID,
        action_id: UUID,
        *,
        idempotency_key: str,
        commit: bool = True,
    ) -> ActionExecution:
        """Execute a validated action via the registry (placeholder handlers in M8.1).

        Never mutates PO/GRN/Invoice or reconciliation exception financial status.
        """
        plan = self.get_plan(plan_id)
        action = self.get_action(plan_id, action_id)
        exception_before = self._session.get(
            ReconciliationException, plan.reconciliation_exception_id
        )
        assert exception_before is not None
        status_before = exception_before.status

        # Idempotent replay must short-circuit before plan/action terminal checks.
        existing_by_key = self._session.scalar(
            select(ActionExecution).where(ActionExecution.idempotency_key == idempotency_key)
        )
        if existing_by_key is not None and existing_by_key.proposed_action_id == action.id:
            return existing_by_key

        existing_for_action = list(
            self._session.scalars(
                select(ActionExecution).where(ActionExecution.proposed_action_id == action.id)
            ).all()
        )
        try:
            validate_execution(
                action,
                idempotency_key=idempotency_key,
                existing_by_key=existing_by_key,
                existing_for_action=existing_for_action,
            )
        except GuardrailError as exc:
            raise ResolutionValidationError(str(exc)) from exc

        try:
            validate_action(action, plan=plan, registry=self._registry)
            validate_approval(action, list(action.approvals))
        except GuardrailError as exc:
            raise ResolutionValidationError(str(exc)) from exc

        now = datetime.now(UTC)
        execution = ActionExecution(
            proposed_action_id=action.id,
            execution_status=ExecutionStatus.PENDING.value,
            idempotency_key=idempotency_key,
        )
        try:
            with self._session.begin_nested():
                self._session.add(execution)
                self._session.flush()
        except IntegrityError as exc:
            existing = self._session.scalar(
                select(ActionExecution).where(
                    ActionExecution.idempotency_key == idempotency_key
                )
            )
            if existing is not None and existing.proposed_action_id == action.id:
                return existing
            raise ResolutionConflictError(
                f"Duplicate idempotency_key: {idempotency_key}"
            ) from exc

        # Advance plan/action toward EXECUTING.
        plan_status = ResolutionPlanStatus(plan.status)
        if plan_status in {
            ResolutionPlanStatus.APPROVED,
            ResolutionPlanStatus.APPROVAL_REQUIRED,
            ResolutionPlanStatus.FAILED,
        }:
            assert_plan_transition(plan_status, ResolutionPlanStatus.EXECUTING)
            plan.status = ResolutionPlanStatus.EXECUTING.value
        elif plan_status is not ResolutionPlanStatus.EXECUTING:
            raise ResolutionValidationError(
                f"Plan status {plan_status.value} cannot start execution."
            )

        action_status = ProposedActionStatus(action.status)
        if action_status in {
            ProposedActionStatus.APPROVED,
            ProposedActionStatus.PENDING,
            ProposedActionStatus.FAILED,
        }:
            assert_action_transition(action_status, ProposedActionStatus.EXECUTING)
        else:
            raise ResolutionValidationError(
                f"Action status {action_status.value} cannot start execution."
            )
        action.status = ProposedActionStatus.EXECUTING.value

        assert_execution_transition(ExecutionStatus.PENDING, ExecutionStatus.RUNNING)
        execution.execution_status = ExecutionStatus.RUNNING.value
        execution.started_at = now
        self._session.flush()

        try:
            handler = self._registry.get(action.action_type)
            typed = handler.validate_parameters(dict(action.parameters or {}))
            ctx = ActionExecutionContext(
                session=self._session,
                plan=plan,
                action=action,
                exception=exception_before,
                idempotency_key=idempotency_key,
            )
            # Nested savepoint: handler side effects roll back on failure while
            # the ActionExecution FAILED audit row is preserved.
            with self._session.begin_nested():
                result = handler.execute(typed, ctx)
            assert_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.SUCCEEDED)
            execution.execution_status = ExecutionStatus.SUCCEEDED.value
            execution.completed_at = datetime.now(UTC)
            execution.result = result.model_dump(mode="json")
            assert_action_transition(
                ProposedActionStatus.EXECUTING, ProposedActionStatus.COMPLETED
            )
            action.status = ProposedActionStatus.COMPLETED.value
        except Exception as exc:  # noqa: BLE001 — record failure, re-raise typed
            assert_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.FAILED)
            execution.execution_status = ExecutionStatus.FAILED.value
            execution.completed_at = datetime.now(UTC)
            execution.error_code = type(exc).__name__
            execution.error_message = str(exc)
            execution.result = {
                "success": False,
                "status": "failed",
                "message": str(exc),
                "error_code": type(exc).__name__,
            }
            assert_action_transition(
                ProposedActionStatus.EXECUTING, ProposedActionStatus.FAILED
            )
            action.status = ProposedActionStatus.FAILED.value
            plan.status = ResolutionPlanStatus.FAILED.value
            if commit:
                self._session.commit()
            else:
                self._session.flush()
            raise ResolutionValidationError(f"Action execution failed: {exc}") from exc

        self._refresh_plan_completion(plan)

        # Invariant: M2 exception status is never changed by resolution execution.
        self._session.refresh(exception_before)
        if exception_before.status != status_before:
            exception_before.status = status_before

        if commit:
            self._session.commit()
            return self._session.get(ActionExecution, execution.id)  # type: ignore[return-value]
        self._session.flush()
        return execution

    def _record_decision(
        self,
        plan_id: UUID,
        action_id: UUID,
        *,
        decision: ApprovalDecision,
        reviewer: str,
        reason: str | None,
        commit: bool,
    ) -> ActionApproval:
        if not reviewer or not reviewer.strip():
            raise ResolutionValidationError("reviewer is required.")

        plan = self.get_plan(plan_id)
        if ResolutionPlanStatus(plan.status) is ResolutionPlanStatus.CANCELLED:
            raise ResolutionValidationError("Cannot decide actions on a cancelled plan.")

        action = self.get_action(plan_id, action_id)
        action_status = ProposedActionStatus(action.status)
        if action_status in {
            ProposedActionStatus.COMPLETED,
            ProposedActionStatus.EXECUTING,
            ProposedActionStatus.CANCELLED,
        }:
            raise ResolutionValidationError(
                f"Cannot record approval for action in status {action_status.value}."
            )

        target = (
            ProposedActionStatus.APPROVED
            if decision is ApprovalDecision.APPROVED
            else ProposedActionStatus.REJECTED
        )
        if action_status is not target:
            assert_action_transition(action_status, target)
        action.status = target.value

        now = datetime.now(UTC)
        approval = ActionApproval(
            proposed_action_id=action.id,
            decision=decision.value,
            reviewer=reviewer.strip(),
            reason=reason,
            decided_at=now,
        )
        self._session.add(approval)
        self._session.flush()
        self._refresh_plan_after_decision(plan)

        if commit:
            self._session.commit()
            return self._session.get(ActionApproval, approval.id)  # type: ignore[return-value]
        self._session.flush()
        return approval

    def _refresh_plan_after_decision(self, plan: ResolutionPlan) -> None:
        actions = self.list_actions(plan.id)
        if not actions:
            return
        statuses = {ProposedActionStatus(a.status) for a in actions}
        plan_status = ResolutionPlanStatus(plan.status)

        if all(s is ProposedActionStatus.REJECTED for s in statuses):
            if plan_status not in {
                ResolutionPlanStatus.REJECTED,
                ResolutionPlanStatus.CANCELLED,
            }:
                if plan_status in {
                    ResolutionPlanStatus.PROPOSED,
                    ResolutionPlanStatus.APPROVAL_REQUIRED,
                }:
                    assert_plan_transition(plan_status, ResolutionPlanStatus.REJECTED)
                plan.status = ResolutionPlanStatus.REJECTED.value
            return

        if (
            all(
                s in {ProposedActionStatus.APPROVED, ProposedActionStatus.REJECTED}
                for s in statuses
            )
            and any(s is ProposedActionStatus.APPROVED for s in statuses)
            and plan_status is ResolutionPlanStatus.APPROVAL_REQUIRED
        ):
            assert_plan_transition(plan_status, ResolutionPlanStatus.APPROVED)
            plan.status = ResolutionPlanStatus.APPROVED.value

    def _refresh_plan_completion(self, plan: ResolutionPlan) -> None:
        actions = self.list_actions(plan.id)
        executable = [
            a
            for a in actions
            if ProposedActionStatus(a.status) is not ProposedActionStatus.REJECTED
        ]
        if not executable:
            return
        if all(
            ProposedActionStatus(a.status) is ProposedActionStatus.COMPLETED
            for a in executable
        ):
            plan_status = ResolutionPlanStatus(plan.status)
            if plan_status is ResolutionPlanStatus.EXECUTING:
                assert_plan_transition(plan_status, ResolutionPlanStatus.COMPLETED)
                plan.status = ResolutionPlanStatus.COMPLETED.value


# Re-export for callers that want service-local access.
__all__ = [
    "InvalidResolutionTransitionError",
    "ResolutionConflictError",
    "ResolutionNotFoundError",
    "ResolutionService",
    "ResolutionServiceError",
    "ResolutionValidationError",
]
