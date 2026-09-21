"""Approved ProposedAction immutability (M8.5 hardening).

Once an action leaves PENDING, its identity fields are frozen. On APPROVED,
a SHA-256 hash of canonical parameters is stored so execution can prove the
payload matches what the human authorized.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session, object_session

from app.domain.enums import ProposedActionStatus

# Fields that must not change after the action leaves PENDING.
PROTECTED_FIELDS = frozenset(
    {
        "action_type",
        "parameters",
        "action_order",
        "requires_approval",
    }
)

# Statuses where identity fields are immutable.
LOCKED_STATUSES = frozenset(
    {
        ProposedActionStatus.APPROVED.value,
        ProposedActionStatus.EXECUTING.value,
        ProposedActionStatus.COMPLETED.value,
        ProposedActionStatus.FAILED.value,
        ProposedActionStatus.REJECTED.value,
        ProposedActionStatus.CANCELLED.value,
    }
)


class ProposedActionImmutabilityError(ValueError):
    """Raised when a locked ProposedAction identity field is mutated."""


def canonicalize_parameters(parameters: dict[str, Any] | None) -> str:
    """Stable JSON canonical form for hashing (sorted keys, no whitespace)."""
    payload = parameters if isinstance(parameters, dict) else {}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_parameters_hash(parameters: dict[str, Any] | None) -> str:
    """SHA-256 hex digest of canonical parameters."""
    canonical = canonicalize_parameters(parameters)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_parameters_match_approved_hash(
    *,
    parameters: dict[str, Any] | None,
    approved_parameters_hash: str | None,
) -> None:
    """Reject execution when current parameters differ from the approval snapshot."""
    if not approved_parameters_hash:
        raise ProposedActionImmutabilityError(
            "approved_parameters_hash is missing; cannot verify approved parameters."
        )
    current = compute_parameters_hash(parameters)
    if current != approved_parameters_hash:
        raise ProposedActionImmutabilityError(
            "ProposedAction parameters do not match approved_parameters_hash; "
            "execution rejected."
        )


def assert_identity_mutable(status: str) -> None:
    """Raise if identity fields must not be changed for this status."""
    if status in LOCKED_STATUSES:
        raise ProposedActionImmutabilityError(
            f"Cannot mutate ProposedAction identity fields after status={status}."
        )


def _protect_on_before_flush(
    session: Session,
    _flush_context: Any,
    _instances: Any,
) -> None:
    from app.db.models import ProposedAction

    for obj in session.dirty:
        if not isinstance(obj, ProposedAction):
            continue
        state = sa_inspect(obj)
        status_hist = state.attrs.status.history
        # Prefer the committed/prior status when status is changing this flush.
        prior_status = (
            str(status_hist.deleted[0]) if status_hist.deleted else str(obj.status)
        )

        # Still PENDING (and not transitioning into a locked status): mutable.
        new_status = str(obj.status)
        entering_lock = (
            prior_status not in LOCKED_STATUSES and new_status in LOCKED_STATUSES
        )
        already_locked = prior_status in LOCKED_STATUSES

        if not already_locked and not entering_lock:
            continue

        for field in PROTECTED_FIELDS:
            hist = state.attrs[field].history
            if hist.has_changes():
                raise ProposedActionImmutabilityError(
                    f"Cannot mutate ProposedAction.{field} after status="
                    f"{prior_status if already_locked else new_status}."
                )

        # Once a hash exists, it must not be replaced (except first write on approve).
        hash_hist = state.attrs.approved_parameters_hash.history
        if hash_hist.has_changes() and hash_hist.deleted and hash_hist.deleted[0]:
            raise ProposedActionImmutabilityError(
                "Cannot replace approved_parameters_hash after it has been set."
            )


_LISTENER_REGISTERED = False


def register_proposed_action_immutability() -> None:
    """Idempotently register the Session before_flush immutability guard."""
    global _LISTENER_REGISTERED
    if _LISTENER_REGISTERED:
        return
    event.listen(Session, "before_flush", _protect_on_before_flush)
    _LISTENER_REGISTERED = True


def ensure_hash_on_approve(action: Any) -> str:
    """Set and return approved_parameters_hash when approving."""
    digest = compute_parameters_hash(dict(action.parameters or {}))
    action.approved_parameters_hash = digest
    # Touch session so hash is persisted with the approval transition.
    session = object_session(action)
    if session is not None:
        session.add(action)
    return digest
