"""M8.5 controlled action execution.

Deterministic, application-controlled execution only:
ProposedAction → Guardrails → ActionRegistry → Typed Handler → ActionExecution

Never calls Gemini, never invents actions, never mutates financial truth.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    ActionExecution,
    ProposedAction,
    ReconciliationException,
    ResolutionPlan,
)
from app.domain.enums import (
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionAuditActorType,
    ResolutionAuditEventType,
    ResolutionPlanStatus,
)
from app.resolution.audit import ResolutionAuditWriter, parameters_hash
from app.resolution.context import ActionExecutionContext
from app.resolution.guardrails import (
    GuardrailError,
    aggregate_plan_status,
    validate_action,
    validate_action_order,
    validate_approval,
    validate_execution,
)
from app.resolution.immutability import (
    ProposedActionImmutabilityError,
    assert_parameters_match_approved_hash,
)
from app.resolution.registry import ActionRegistry, build_default_registry
from app.resolution.transitions import (
    InvalidResolutionTransitionError,
    assert_action_transition,
    assert_execution_transition,
    assert_plan_transition,
)


class ResolutionExecutionError(Exception):
    """Base execution-service error."""


class ResolutionExecutionNotFoundError(ResolutionExecutionError):
    """Plan or action not found."""


class ResolutionExecutionValidationError(ResolutionExecutionError):
    """Guardrail or state validation failure."""


class ResolutionExecutionConflictError(ResolutionExecutionError):
    """Idempotency or concurrency conflict."""


class ResolutionExecutionService:
    """Execute approved proposed actions via the ActionRegistry only."""

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

    def execute_action(
        self,
        plan_id: UUID,
        action_id: UUID,
        *,
        idempotency_key: str,
        commit: bool = True,
    ) -> ActionExecution:
        """Run one registered handler under guardrails + savepoint + locking.

        Client cannot override action_type, parameters, status, or handler.
        """
        key = idempotency_key.strip() if idempotency_key else ""
        if not key:
            raise ResolutionExecutionValidationError("idempotency_key is required.")

        # Lock the proposed action row to serialize concurrent execute attempts.
        action = self._lock_action(plan_id, action_id)
        plan = self._session.get(ResolutionPlan, plan_id)
        if plan is None:
            raise ResolutionExecutionNotFoundError(
                f"Resolution plan {plan_id} was not found."
            )

        exception_before = self._session.get(
            ReconciliationException, plan.reconciliation_exception_id
        )
        if exception_before is None:
            raise ResolutionExecutionNotFoundError(
                f"Reconciliation exception {plan.reconciliation_exception_id} was not found."
            )
        status_before = exception_before.status

        # Idempotent replay (same key) before further state checks.
        existing_by_key = self._session.scalar(
            select(ActionExecution).where(ActionExecution.idempotency_key == key)
        )
        if existing_by_key is not None and existing_by_key.proposed_action_id == action.id:
            return existing_by_key

        existing_for_action = list(
            self._session.scalars(
                select(ActionExecution).where(ActionExecution.proposed_action_id == action.id)
            ).all()
        )
        try:
            replay = validate_execution(
                action,
                idempotency_key=key,
                existing_by_key=existing_by_key,
                existing_for_action=existing_for_action,
            )
        except GuardrailError as exc:
            raise ResolutionExecutionValidationError(str(exc)) from exc
        if replay is not None:
            return replay

        siblings = list(
            self._session.scalars(
                select(ProposedAction)
                .where(ProposedAction.resolution_plan_id == plan_id)
                .order_by(ProposedAction.action_order)
            ).all()
        )

        try:
            validate_action(action, plan=plan, registry=self._registry)
            validate_action_order(action, siblings)
            # Reload approvals under the locked action.
            self._session.refresh(action, attribute_names=["approvals"])
            validate_approval(action, list(action.approvals), registry=self._registry)
            handler = self._registry.get(action.action_type)
            if handler.requires_approval or getattr(action, "approved_parameters_hash", None):
                assert_parameters_match_approved_hash(
                    parameters=dict(action.parameters or {}),
                    approved_parameters_hash=getattr(action, "approved_parameters_hash", None),
                )
        except (GuardrailError, ProposedActionImmutabilityError) as exc:
            if isinstance(exc, ProposedActionImmutabilityError):
                ResolutionAuditWriter(self._session).record(
                    event_type=ResolutionAuditEventType.EXECUTION_FAILED,
                    actor_type=ResolutionAuditActorType.SYSTEM,
                    resolution_plan_id=plan.id,
                    proposed_action_id=action.id,
                    event_data={
                        "error_code": "PARAMETERS_HASH_MISMATCH",
                        "message": str(exc)[:2000],
                        "approved_parameters_hash": getattr(
                            action, "approved_parameters_hash", None
                        ),
                        "executed_parameters_hash": parameters_hash(
                            dict(action.parameters or {})
                        ),
                    },
                )
                if commit:
                    self._session.commit()
            raise ResolutionExecutionValidationError(str(exc)) from exc

        now = datetime.now(UTC)
        execution = ActionExecution(
            proposed_action_id=action.id,
            execution_status=ExecutionStatus.PENDING.value,
            idempotency_key=key,
        )
        try:
            with self._session.begin_nested():
                self._session.add(execution)
                self._session.flush()
        except IntegrityError as exc:
            existing = self._session.scalar(
                select(ActionExecution).where(ActionExecution.idempotency_key == key)
            )
            if existing is not None and existing.proposed_action_id == action.id:
                return existing
            raise ResolutionExecutionConflictError(
                f"Duplicate idempotency_key: {key}"
            ) from exc

        self._advance_to_executing(plan, action, execution, now)

        audit = ResolutionAuditWriter(self._session)
        executed_hash = parameters_hash(dict(action.parameters or {}))
        audit.record(
            event_type=ResolutionAuditEventType.EXECUTION_STARTED,
            actor_type=ResolutionAuditActorType.SYSTEM,
            resolution_plan_id=plan.id,
            proposed_action_id=action.id,
            action_execution_id=execution.id,
            event_data={
                "idempotency_key": key,
                "action_type": action.action_type,
                "executed_parameters_hash": executed_hash,
                "approved_parameters_hash": getattr(action, "approved_parameters_hash", None),
            },
        )

        try:
            handler = self._registry.get(action.action_type)
            typed = handler.validate_parameters(dict(action.parameters or {}))
            ctx = ActionExecutionContext(
                session=self._session,
                plan=plan,
                action=action,
                exception=exception_before,
                idempotency_key=key,
            )
            # Handler side effects roll back on failure; ActionExecution FAILED is kept.
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

            workflow_event = (
                ResolutionAuditEventType.WORKFLOW_REUSED
                if result.status == "already_exists"
                else ResolutionAuditEventType.WORKFLOW_CREATED
            )
            audit.record(
                event_type=workflow_event,
                actor_type=ResolutionAuditActorType.SYSTEM,
                resolution_plan_id=plan.id,
                proposed_action_id=action.id,
                action_execution_id=execution.id,
                event_data={
                    "workflow_type": action.action_type,
                    "reference_id": str(result.reference_id) if result.reference_id else None,
                    "status": result.status,
                    "message": result.message,
                },
            )
            audit.record(
                event_type=ResolutionAuditEventType.EXECUTION_SUCCEEDED,
                actor_type=ResolutionAuditActorType.SYSTEM,
                resolution_plan_id=plan.id,
                proposed_action_id=action.id,
                action_execution_id=execution.id,
                event_data={
                    "execution_id": str(execution.id),
                    "result": execution.result,
                    "reference_id": str(result.reference_id) if result.reference_id else None,
                    "executed_parameters_hash": executed_hash,
                    "approved_parameters_hash": getattr(
                        action, "approved_parameters_hash", None
                    ),
                },
            )
        except Exception as exc:  # noqa: BLE001 — record failure, re-raise typed
            assert_execution_transition(ExecutionStatus.RUNNING, ExecutionStatus.FAILED)
            execution.execution_status = ExecutionStatus.FAILED.value
            execution.completed_at = datetime.now(UTC)
            execution.error_code = type(exc).__name__
            # Persist a safe, bounded message (no secrets / unrestricted traces).
            safe_message = str(exc)[:2000]
            execution.error_message = safe_message
            execution.result = {
                "success": False,
                "status": "failed",
                "message": safe_message,
                "error_code": type(exc).__name__,
            }
            assert_action_transition(
                ProposedActionStatus.EXECUTING, ProposedActionStatus.FAILED
            )
            action.status = ProposedActionStatus.FAILED.value
            self._apply_plan_status(plan, ResolutionPlanStatus.FAILED)
            audit.record(
                event_type=ResolutionAuditEventType.EXECUTION_FAILED,
                actor_type=ResolutionAuditActorType.SYSTEM,
                resolution_plan_id=plan.id,
                proposed_action_id=action.id,
                action_execution_id=execution.id,
                event_data={
                    "execution_id": str(execution.id),
                    "error_code": type(exc).__name__,
                    "message": safe_message,
                    "executed_parameters_hash": executed_hash,
                },
            )
            self._restore_exception_status(exception_before, status_before)
            if commit:
                self._session.commit()
            else:
                self._session.flush()
            raise ResolutionExecutionValidationError(
                f"Action execution failed: {exc}"
            ) from exc

        self._refresh_plan_after_execution(plan)
        self._restore_exception_status(exception_before, status_before)

        if commit:
            self._session.commit()
            return self._session.get(ActionExecution, execution.id)  # type: ignore[return-value]
        self._session.flush()
        return execution

    def _lock_action(self, plan_id: UUID, action_id: UUID) -> ProposedAction:
        """Load ProposedAction with a row lock when the dialect supports it."""
        stmt = (
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
        # SQLite does not usefully support FOR UPDATE; Postgres/MySQL do.
        bind = self._session.get_bind()
        if bind is not None and bind.dialect.name not in {"sqlite"}:
            stmt = stmt.with_for_update()
        action = self._session.scalar(stmt)
        if action is None:
            raise ResolutionExecutionNotFoundError(
                f"Proposed action {action_id} was not found on plan {plan_id}."
            )
        return action

    def _advance_to_executing(
        self,
        plan: ResolutionPlan,
        action: ProposedAction,
        execution: ActionExecution,
        now: datetime,
    ) -> None:
        plan_status = ResolutionPlanStatus(plan.status)
        if plan_status in {
            ResolutionPlanStatus.APPROVED,
            ResolutionPlanStatus.APPROVAL_REQUIRED,
            ResolutionPlanStatus.FAILED,
        }:
            assert_plan_transition(plan_status, ResolutionPlanStatus.EXECUTING)
            plan.status = ResolutionPlanStatus.EXECUTING.value
        elif plan_status is not ResolutionPlanStatus.EXECUTING:
            raise ResolutionExecutionValidationError(
                f"Plan status {plan_status.value} cannot start execution."
            )

        action_status = ProposedActionStatus(action.status)
        if action_status in {
            ProposedActionStatus.APPROVED,
            ProposedActionStatus.PENDING,
            ProposedActionStatus.FAILED,
        }:
            try:
                assert_action_transition(action_status, ProposedActionStatus.EXECUTING)
            except InvalidResolutionTransitionError as exc:
                raise ResolutionExecutionValidationError(str(exc)) from exc
        else:
            raise ResolutionExecutionValidationError(
                f"Action status {action_status.value} cannot start execution."
            )
        action.status = ProposedActionStatus.EXECUTING.value

        assert_execution_transition(ExecutionStatus.PENDING, ExecutionStatus.RUNNING)
        execution.execution_status = ExecutionStatus.RUNNING.value
        execution.started_at = now
        self._session.flush()

    def _refresh_plan_after_execution(self, plan: ResolutionPlan) -> None:
        actions = list(
            self._session.scalars(
                select(ProposedAction)
                .where(ProposedAction.resolution_plan_id == plan.id)
                .order_by(ProposedAction.action_order)
            ).all()
        )
        desired = aggregate_plan_status(actions)
        if desired is None:
            return
        self._apply_plan_status(plan, desired)

    def _apply_plan_status(
        self,
        plan: ResolutionPlan,
        desired: ResolutionPlanStatus,
    ) -> None:
        current = ResolutionPlanStatus(plan.status)
        if current is desired:
            return
        if current in {
            ResolutionPlanStatus.CANCELLED,
            ResolutionPlanStatus.COMPLETED,
            ResolutionPlanStatus.NO_ACTION_RECOMMENDED,
        }:
            return
        try:
            assert_plan_transition(current, desired)
        except InvalidResolutionTransitionError as exc:
            # If already at a compatible aggregate, skip; otherwise surface.
            if desired.value == plan.status:
                return
            raise ResolutionExecutionValidationError(str(exc)) from exc
        plan.status = desired.value

    @staticmethod
    def _restore_exception_status(
        exception: ReconciliationException,
        status_before: str,
    ) -> None:
        """Hard invariant: resolution execution never mutates M2 financial truth."""
        if exception.status != status_before:
            exception.status = status_before


def execution_api_payload(
    *,
    plan: ResolutionPlan,
    action: ProposedAction,
    execution: ActionExecution,
) -> dict[str, Any]:
    """Structured execute API body (never exposes secrets)."""
    return {
        "plan_id": plan.id,
        "action_id": action.id,
        "action_type": action.action_type,
        "execution_id": execution.id,
        "execution_status": execution.execution_status,
        "action_status": action.status,
        "plan_status": plan.status,
        "idempotency_key": execution.idempotency_key,
        "result": execution.result,
        "error_code": execution.error_code,
        "error_message": execution.error_message,
        "started_at": execution.started_at,
        "completed_at": execution.completed_at,
    }
