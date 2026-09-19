"""Explicit status transitions for resolution plans, actions, and executions."""

from __future__ import annotations

from app.domain.enums import ExecutionStatus, ProposedActionStatus, ResolutionPlanStatus

PLAN_ALLOWED_TRANSITIONS: dict[ResolutionPlanStatus, frozenset[ResolutionPlanStatus]] = {
    ResolutionPlanStatus.PROPOSED: frozenset(
        {
            ResolutionPlanStatus.APPROVAL_REQUIRED,
            ResolutionPlanStatus.APPROVED,
            ResolutionPlanStatus.REJECTED,
            ResolutionPlanStatus.CANCELLED,
        }
    ),
    ResolutionPlanStatus.APPROVAL_REQUIRED: frozenset(
        {
            ResolutionPlanStatus.APPROVED,
            ResolutionPlanStatus.REJECTED,
            ResolutionPlanStatus.EXECUTING,
            ResolutionPlanStatus.CANCELLED,
        }
    ),
    ResolutionPlanStatus.APPROVED: frozenset(
        {
            ResolutionPlanStatus.EXECUTING,
            ResolutionPlanStatus.CANCELLED,
        }
    ),
    ResolutionPlanStatus.EXECUTING: frozenset(
        {
            ResolutionPlanStatus.COMPLETED,
            ResolutionPlanStatus.FAILED,
            ResolutionPlanStatus.CANCELLED,
        }
    ),
    # Allow retry after a failed execution attempt.
    ResolutionPlanStatus.FAILED: frozenset({ResolutionPlanStatus.EXECUTING}),
    ResolutionPlanStatus.REJECTED: frozenset(),
    ResolutionPlanStatus.COMPLETED: frozenset(),
    ResolutionPlanStatus.CANCELLED: frozenset(),
}

ACTION_ALLOWED_TRANSITIONS: dict[ProposedActionStatus, frozenset[ProposedActionStatus]] = {
    ProposedActionStatus.PENDING: frozenset(
        {
            ProposedActionStatus.APPROVED,
            ProposedActionStatus.REJECTED,
            ProposedActionStatus.CANCELLED,
            # Approval-not-required actions may execute directly from PENDING.
            ProposedActionStatus.EXECUTING,
        }
    ),
    ProposedActionStatus.APPROVED: frozenset(
        {
            ProposedActionStatus.EXECUTING,
            ProposedActionStatus.CANCELLED,
        }
    ),
    ProposedActionStatus.EXECUTING: frozenset(
        {
            ProposedActionStatus.COMPLETED,
            ProposedActionStatus.FAILED,
        }
    ),
    # Failed executions may be retried with a new idempotency key.
    ProposedActionStatus.FAILED: frozenset({ProposedActionStatus.EXECUTING}),
    ProposedActionStatus.REJECTED: frozenset(),
    ProposedActionStatus.COMPLETED: frozenset(),
    ProposedActionStatus.CANCELLED: frozenset(),
}

EXECUTION_ALLOWED_TRANSITIONS: dict[ExecutionStatus, frozenset[ExecutionStatus]] = {
    ExecutionStatus.PENDING: frozenset({ExecutionStatus.RUNNING, ExecutionStatus.FAILED}),
    ExecutionStatus.RUNNING: frozenset({ExecutionStatus.SUCCEEDED, ExecutionStatus.FAILED}),
    ExecutionStatus.SUCCEEDED: frozenset(),
    ExecutionStatus.FAILED: frozenset(),
}

TERMINAL_PLAN_STATUSES = frozenset(
    {
        ResolutionPlanStatus.REJECTED,
        ResolutionPlanStatus.COMPLETED,
        ResolutionPlanStatus.FAILED,
        ResolutionPlanStatus.CANCELLED,
    }
)

NON_EXECUTABLE_PLAN_STATUSES = frozenset(
    {
        ResolutionPlanStatus.REJECTED,
        ResolutionPlanStatus.CANCELLED,
        ResolutionPlanStatus.COMPLETED,
        # FAILED is retryable via FAILED → EXECUTING.
    }
)


class InvalidResolutionTransitionError(Exception):
    """Raised when a resolution status transition is not allowed."""


def assert_plan_transition(
    current: ResolutionPlanStatus,
    target: ResolutionPlanStatus,
) -> None:
    if target not in PLAN_ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidResolutionTransitionError(
            f"Cannot transition resolution plan from {current.value} to {target.value}."
        )


def assert_action_transition(
    current: ProposedActionStatus,
    target: ProposedActionStatus,
) -> None:
    if target not in ACTION_ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidResolutionTransitionError(
            f"Cannot transition proposed action from {current.value} to {target.value}."
        )


def assert_execution_transition(
    current: ExecutionStatus,
    target: ExecutionStatus,
) -> None:
    if target not in EXECUTION_ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidResolutionTransitionError(
            f"Cannot transition execution from {current.value} to {target.value}."
        )
