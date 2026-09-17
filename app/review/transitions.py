"""Explicit ReviewStatus state machine."""

from __future__ import annotations

from app.domain.enums import ReviewStatus

ALLOWED_TRANSITIONS: dict[ReviewStatus, frozenset[ReviewStatus]] = {
    ReviewStatus.PENDING: frozenset(
        {
            ReviewStatus.IN_REVIEW,
            ReviewStatus.APPROVED,
            ReviewStatus.CORRECTED,
            ReviewStatus.REJECTED,
        }
    ),
    ReviewStatus.IN_REVIEW: frozenset(
        {
            ReviewStatus.APPROVED,
            ReviewStatus.CORRECTED,
            ReviewStatus.REJECTED,
        }
    ),
    ReviewStatus.CORRECTED: frozenset({ReviewStatus.APPROVED}),
    ReviewStatus.APPROVED: frozenset(),
    ReviewStatus.REJECTED: frozenset(),
}

TERMINAL_STATUSES = frozenset(
    {
        ReviewStatus.APPROVED,
        ReviewStatus.CORRECTED,
        ReviewStatus.REJECTED,
    }
)

PROMOTABLE_STATUSES = frozenset(
    {
        ReviewStatus.APPROVED,
        ReviewStatus.CORRECTED,
    }
)


class InvalidReviewTransitionError(Exception):
    """Raised when a status transition is not allowed."""


def assert_transition(current: ReviewStatus, target: ReviewStatus) -> None:
    """Raise if ``current → target`` is not an allowed transition."""
    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise InvalidReviewTransitionError(
            f"Cannot transition review task from {current.value} to {target.value}."
        )
