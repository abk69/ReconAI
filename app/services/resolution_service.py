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
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.resolution.contracts import ActionRequest, parse_action_request
from app.resolution.immutability import ensure_hash_on_approve
from app.resolution.registry import ActionRegistry, build_default_registry
from app.resolution.reviewer import InvalidReviewerError, validate_reviewer
from app.resolution.transitions import (
    InvalidResolutionTransitionError,
    assert_action_transition,
    assert_plan_transition,
)
from app.services.resolution_execution_service import (
    ResolutionExecutionConflictError,
    ResolutionExecutionNotFoundError,
    ResolutionExecutionService,
    ResolutionExecutionValidationError,
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
            # Registry is authoritative — never trust client requires_approval.
            requires_approval = handler.requires_approval
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
        comment: str | None = None,
        idempotency_key: str | None = None,
        commit: bool = True,
    ) -> ActionApproval:
        """Record an APPROVED decision only — does not execute the action."""
        return self._record_decision(
            plan_id,
            action_id,
            decision=ApprovalDecision.APPROVED,
            reviewer=reviewer,
            reason=comment if comment is not None else reason,
            idempotency_key=idempotency_key,
            commit=commit,
        )

    def reject_action(
        self,
        plan_id: UUID,
        action_id: UUID,
        *,
        reviewer: str,
        reason: str | None = None,
        comment: str | None = None,
        idempotency_key: str | None = None,
        commit: bool = True,
    ) -> ActionApproval:
        """Record a REJECTED decision only — does not execute the action."""
        return self._record_decision(
            plan_id,
            action_id,
            decision=ApprovalDecision.REJECTED,
            reviewer=reviewer,
            reason=comment if comment is not None else reason,
            idempotency_key=idempotency_key,
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
        """Delegate to ResolutionExecutionService (M8.5).

        Never mutates PO/GRN/Invoice or reconciliation exception financial status.
        Never calls Gemini.
        """
        executor = ResolutionExecutionService(self._session, registry=self._registry)
        try:
            return executor.execute_action(
                plan_id,
                action_id,
                idempotency_key=idempotency_key,
                commit=commit,
            )
        except ResolutionExecutionNotFoundError as exc:
            raise ResolutionNotFoundError(str(exc)) from exc
        except ResolutionExecutionConflictError as exc:
            raise ResolutionConflictError(str(exc)) from exc
        except ResolutionExecutionValidationError as exc:
            raise ResolutionValidationError(str(exc)) from exc

    def _record_decision(
        self,
        plan_id: UUID,
        action_id: UUID,
        *,
        decision: ApprovalDecision,
        reviewer: str,
        reason: str | None,
        idempotency_key: str | None,
        commit: bool,
    ) -> ActionApproval:
        try:
            reviewer_id = validate_reviewer(reviewer)
        except InvalidReviewerError as exc:
            raise ResolutionValidationError(str(exc)) from exc

        key = idempotency_key.strip() if idempotency_key else None
        if idempotency_key is not None and not key:
            raise ResolutionValidationError("idempotency_key must not be blank.")

        plan = self.get_plan(plan_id)
        if ResolutionPlanStatus(plan.status) is ResolutionPlanStatus.CANCELLED:
            raise ResolutionValidationError("Cannot decide actions on a cancelled plan.")

        action = self.get_action(plan_id, action_id)

        # Idempotent replay by key — same decision returns existing row.
        if key:
            existing_by_key = self._session.scalar(
                select(ActionApproval).where(ActionApproval.idempotency_key == key)
            )
            if existing_by_key is not None:
                if existing_by_key.proposed_action_id != action.id:
                    raise ResolutionConflictError(
                        f"idempotency_key is already used by a different action: {key}"
                    )
                if existing_by_key.decision != decision.value:
                    raise ResolutionConflictError(
                        "idempotency_key was previously used with a conflicting decision."
                    )
                return existing_by_key

        action_status = ProposedActionStatus(action.status)
        if action_status in {
            ProposedActionStatus.COMPLETED,
            ProposedActionStatus.EXECUTING,
            ProposedActionStatus.CANCELLED,
            ProposedActionStatus.FAILED,
        }:
            raise ResolutionValidationError(
                f"Cannot record approval for action in status {action_status.value}."
            )

        target = (
            ProposedActionStatus.APPROVED
            if decision is ApprovalDecision.APPROVED
            else ProposedActionStatus.REJECTED
        )

        # Duplicate same decision without a key: return the latest matching row
        # (idempotent). Do not append a conflicting second decision.
        if action_status is target:
            prior = [
                a
                for a in action.approvals
                if a.decision == decision.value
            ]
            if prior:
                return max(
                    prior,
                    key=lambda a: (
                        a.created_at or datetime.min.replace(tzinfo=UTC),
                        a.decided_at or datetime.min.replace(tzinfo=UTC),
                        str(a.id),
                    ),
                )
            # Status already matches but no audit row — fall through to create one.

        if action_status is not target:
            try:
                assert_action_transition(action_status, target)
            except InvalidResolutionTransitionError as exc:
                raise ResolutionValidationError(str(exc)) from exc

        action.status = target.value
        if decision is ApprovalDecision.APPROVED:
            ensure_hash_on_approve(action)

        now = datetime.now(UTC)
        approval = ActionApproval(
            proposed_action_id=action.id,
            decision=decision.value,
            reviewer=reviewer_id,
            reason=reason,
            idempotency_key=key,
            decided_at=now,
        )
        try:
            with self._session.begin_nested():
                self._session.add(approval)
                self._session.flush()
        except IntegrityError as exc:
            if key:
                existing = self._session.scalar(
                    select(ActionApproval).where(ActionApproval.idempotency_key == key)
                )
                if existing is not None and existing.proposed_action_id == action.id:
                    if existing.decision != decision.value:
                        raise ResolutionConflictError(
                            "idempotency_key was previously used with a conflicting decision."
                        ) from exc
                    return existing
            raise ResolutionConflictError(
                f"Duplicate approval idempotency_key: {key}"
            ) from exc

        self._refresh_plan_after_decision(plan)

        if commit:
            self._session.commit()
            return self._session.get(ActionApproval, approval.id)  # type: ignore[return-value]
        self._session.flush()
        return approval

    def _refresh_plan_after_decision(self, plan: ResolutionPlan) -> None:
        """Deterministic plan status from action statuses (M8.4 — never COMPLETED)."""
        actions = self.list_actions(plan.id)
        if not actions:
            return

        plan_status = ResolutionPlanStatus(plan.status)
        if plan_status in {
            ResolutionPlanStatus.CANCELLED,
            ResolutionPlanStatus.COMPLETED,
            ResolutionPlanStatus.EXECUTING,
            ResolutionPlanStatus.NO_ACTION_RECOMMENDED,
        }:
            return

        statuses = [ProposedActionStatus(a.status) for a in actions]
        has_pending = any(s is ProposedActionStatus.PENDING for s in statuses)
        all_rejected = all(s is ProposedActionStatus.REJECTED for s in statuses)
        any_approved = any(s is ProposedActionStatus.APPROVED for s in statuses)
        any_rejected = any(s is ProposedActionStatus.REJECTED for s in statuses)

        # Still waiting on human decisions for one or more actions.
        if has_pending:
            if plan_status is ResolutionPlanStatus.PROPOSED:
                assert_plan_transition(plan_status, ResolutionPlanStatus.APPROVAL_REQUIRED)
            if plan_status in {
                ResolutionPlanStatus.PROPOSED,
                ResolutionPlanStatus.APPROVAL_REQUIRED,
            }:
                plan.status = ResolutionPlanStatus.APPROVAL_REQUIRED.value
            return

        # Every action decided.
        if all_rejected or (any_rejected and not any_approved):
            if plan_status in {
                ResolutionPlanStatus.PROPOSED,
                ResolutionPlanStatus.APPROVAL_REQUIRED,
            }:
                assert_plan_transition(plan_status, ResolutionPlanStatus.REJECTED)
            plan.status = ResolutionPlanStatus.REJECTED.value
            return

        # At least one approved; remaining are approved or rejected.
        if any_approved and plan_status in {
            ResolutionPlanStatus.APPROVAL_REQUIRED,
            ResolutionPlanStatus.PROPOSED,
        }:
            assert_plan_transition(plan_status, ResolutionPlanStatus.APPROVED)
            plan.status = ResolutionPlanStatus.APPROVED.value

    def _refresh_plan_completion(self, plan: ResolutionPlan) -> None:
        """Legacy hook — execution path uses ResolutionExecutionService aggregation."""
        from app.resolution.guardrails import aggregate_plan_status

        actions = self.list_actions(plan.id)
        desired = aggregate_plan_status(actions)
        if desired is None:
            return
        current = ResolutionPlanStatus(plan.status)
        if current is desired:
            return
        if current in {
            ResolutionPlanStatus.CANCELLED,
            ResolutionPlanStatus.COMPLETED,
            ResolutionPlanStatus.NO_ACTION_RECOMMENDED,
        }:
            return
        assert_plan_transition(current, desired)
        plan.status = desired.value


# Re-export for callers that want service-local access.
__all__ = [
    "InvalidResolutionTransitionError",
    "ResolutionConflictError",
    "ResolutionNotFoundError",
    "ResolutionService",
    "ResolutionServiceError",
    "ResolutionValidationError",
]
