"""Human review domain for M5 extraction candidates."""

from app.review.transitions import ALLOWED_TRANSITIONS, assert_transition

__all__ = ["ALLOWED_TRANSITIONS", "assert_transition"]
