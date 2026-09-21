"""Deterministic guardrails for resolution action execution.

Gemini / LLMs are never consulted here. Validation is pure rule-based checks
against registered actions, typed parameters, approval state, and idempotency.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.db.models import ActionApproval, ActionExecution, ProposedAction, ResolutionPlan
from app.domain.enums import (
    ApprovalDecision,
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.resolution.contracts import parse_action_parameters
from app.resolution.registry import ActionRegistry
from app.resolution.transitions import NON_EXECUTABLE_PLAN_STATUSES


class GuardrailError(Exception):
    """Raised when a deterministic guardrail rejects an action."""


def _aware(dt: datetime | None) -> datetime:
    if dt is None:
        return datetime.min.replace(tzinfo=UTC)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def validate_action(
    action: ProposedAction,
    *,
    plan: ResolutionPlan,
    registry: ActionRegistry,
    parameters: dict[str, Any] | None = None,
) -> None:
    """Reject unknown types, malformed parameters, and cancelled/terminal plans."""
    plan_status = ResolutionPlanStatus(plan.status)
    if plan_status in NON_EXECUTABLE_PLAN_STATUSES:
        raise GuardrailError(
            f"Cannot execute actions for plan in status {plan_status.value}."
        )

    action_status = ProposedActionStatus(action.status)
    if action_status is ProposedActionStatus.REJECTED:
        raise GuardrailError("Rejected actions cannot be executed.")
    if action_status is ProposedActionStatus.CANCELLED:
        raise GuardrailError("Cancelled actions cannot be executed.")
    if action_status is ProposedActionStatus.COMPLETED:
        raise GuardrailError("Action has already completed.")

    if not registry.is_registered(action.action_type):
        raise GuardrailError(f"Unknown or unregistered action type: {action.action_type}.")

    raw_params = parameters if parameters is not None else (action.parameters or {})
    try:
        parse_action_parameters(action.action_type, raw_params)
    except Exception as exc:
        raise GuardrailError(f"Malformed action parameters: {exc}") from exc


def validate_approval(
    action: ProposedAction,
    approvals: list[ActionApproval],
    *,
    registry: ActionRegistry | None = None,
) -> None:
    """Require an APPROVED record when the action definition requires approval.

    The ActionRegistry (when provided) is authoritative for ``requires_approval``.
    Client-supplied or stale flags on the row must not bypass the gate.
    """
    if ProposedActionStatus(action.status) is ProposedActionStatus.REJECTED:
        raise GuardrailError("Rejected actions cannot be executed.")

    requires_approval = action.requires_approval
    if registry is not None and registry.is_registered(action.action_type):
        requires_approval = registry.get(action.action_type).requires_approval

    if not requires_approval:
        return

    if ProposedActionStatus(action.status) is ProposedActionStatus.APPROVED:
        # Status already reflects approval; still require an audit row.
        pass

    approved = any(a.decision == ApprovalDecision.APPROVED.value for a in approvals)
    rejected = any(a.decision == ApprovalDecision.REJECTED.value for a in approvals)

    if rejected and not approved:
        raise GuardrailError("Action was rejected and cannot be executed.")

    # Latest decision wins — append-only log ordered by created_at.
    if approvals:
        latest = max(
            approvals,
            key=lambda a: (_aware(a.created_at), _aware(a.decided_at), str(a.id)),
        )
        if latest.decision == ApprovalDecision.REJECTED.value:
            raise GuardrailError("Latest approval decision is REJECTED.")
        if latest.decision == ApprovalDecision.APPROVED.value:
            return

    if requires_approval and not approved:
        raise GuardrailError(
            "Approval-required actions cannot execute without an APPROVED ActionApproval."
        )


def validate_execution(
    action: ProposedAction,
    *,
    idempotency_key: str,
    existing_by_key: ActionExecution | None,
    existing_for_action: list[ActionExecution],
) -> ActionExecution | None:
    """Enforce idempotency and reject unsafe duplicate execution attempts.

    Returns an existing execution when the same idempotency key is retried
    (caller should return it without re-running the handler).
    """
    if not idempotency_key or not idempotency_key.strip():
        raise GuardrailError("idempotency_key is required.")

    if existing_by_key is not None:
        if existing_by_key.proposed_action_id != action.id:
            raise GuardrailError(
                "idempotency_key is already used by a different proposed action."
            )
        return existing_by_key

    active_or_done = [
        e
        for e in existing_for_action
        if e.execution_status
        in {
            ExecutionStatus.PENDING.value,
            ExecutionStatus.RUNNING.value,
            ExecutionStatus.SUCCEEDED.value,
        }
    ]
    if active_or_done:
        raise GuardrailError(
            "Proposed action already has an active or successful execution; "
            "retry with the original idempotency_key."
        )

    return None
