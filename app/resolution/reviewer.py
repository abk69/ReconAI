"""Controlled reviewer identity for M8.4 human approval.

Production authentication/authorization will integrate here later.
For now the application layer supplies a verified reviewer identifier;
this module only validates that the identity is present and well-formed.
It is never treated as executable data.
"""

from __future__ import annotations

import re

_REVIEWER_PATTERN = re.compile(r"^[\w.@+\- :/]+$", re.UNICODE)
_MAX_LENGTH = 255
_MIN_LENGTH = 1


class InvalidReviewerError(ValueError):
    """Raised when a reviewer identity fails validation."""


def validate_reviewer(reviewer: str | None) -> str:
    """Return a normalized reviewer identity or raise ``InvalidReviewerError``."""
    if reviewer is None:
        raise InvalidReviewerError("reviewer is required.")
    if not isinstance(reviewer, str):
        raise InvalidReviewerError("reviewer must be a string.")
    normalized = reviewer.strip()
    if not normalized:
        raise InvalidReviewerError("reviewer must not be blank.")
    if len(normalized) < _MIN_LENGTH or len(normalized) > _MAX_LENGTH:
        raise InvalidReviewerError(
            f"reviewer length must be between {_MIN_LENGTH} and {_MAX_LENGTH}."
        )
    if not _REVIEWER_PATTERN.fullmatch(normalized):
        raise InvalidReviewerError(
            "reviewer contains invalid characters; use a plain identity string."
        )
    return normalized
