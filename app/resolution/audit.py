"""Append-only resolution audit trail (M8.6).

Events are created only by application services on real state transitions.
Callers cannot fabricate success/approval events.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session

from app.domain.enums import ResolutionAuditActorType, ResolutionAuditEventType
from app.resolution.immutability import compute_parameters_hash

# Keys that must never appear in persisted audit event_data.
_SENSITIVE_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "password",
    "secret",
    "token",
    "authorization",
    "credential",
    "private_key",
)


class ResolutionAuditError(ValueError):
    """Raised for invalid audit writes or mutation attempts."""


def sanitize_event_data(data: dict[str, Any] | None) -> dict[str, Any]:
    """Drop sensitive keys recursively; keep structured metadata only."""
    if not data:
        return {}
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        lowered = str(key).lower()
        if any(frag in lowered for frag in _SENSITIVE_KEY_FRAGMENTS):
            continue
        if isinstance(value, dict):
            cleaned[key] = sanitize_event_data(value)
        elif isinstance(value, list):
            cleaned[key] = [
                sanitize_event_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


class ResolutionAuditWriter:
    """Create immutable resolution audit events from service transitions."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(
        self,
        *,
        event_type: ResolutionAuditEventType,
        actor_type: ResolutionAuditActorType,
        resolution_plan_id: UUID | None = None,
        proposed_action_id: UUID | None = None,
        action_execution_id: UUID | None = None,
        actor_id: str | None = None,
        event_data: dict[str, Any] | None = None,
    ) -> Any:
        from app.db.models import ResolutionAuditEvent

        if not isinstance(event_type, ResolutionAuditEventType):
            raise ResolutionAuditError(f"Unknown audit event type: {event_type!r}")
        if not isinstance(actor_type, ResolutionAuditActorType):
            raise ResolutionAuditError(f"Unknown audit actor type: {actor_type!r}")

        row = ResolutionAuditEvent(
            resolution_plan_id=resolution_plan_id,
            proposed_action_id=proposed_action_id,
            action_execution_id=action_execution_id,
            event_type=event_type.value,
            actor_type=actor_type.value,
            actor_id=(actor_id.strip() if actor_id else None) or None,
            event_data=sanitize_event_data(event_data),
        )
        self._session.add(row)
        self._session.flush()
        return row


def parameters_hash(parameters: dict[str, Any] | None) -> str:
    """Public alias for provenance hashing used in audit payloads."""
    return compute_parameters_hash(parameters)


_AUDIT_LISTENER_REGISTERED = False


def register_resolution_audit_immutability() -> None:
    """Reject updates/deletes of ResolutionAuditEvent rows at flush time."""
    global _AUDIT_LISTENER_REGISTERED
    if _AUDIT_LISTENER_REGISTERED:
        return

    def _protect(session: Session, _flush_context: Any, _instances: Any) -> None:
        from app.db.models import ResolutionAuditEvent

        for obj in session.dirty:
            if isinstance(obj, ResolutionAuditEvent):
                state = sa_inspect(obj)
                for attr in state.attrs:
                    if attr.history.has_changes():
                        raise ResolutionAuditError(
                            "ResolutionAuditEvent rows are append-only; updates are forbidden."
                        )
        for obj in session.deleted:
            if isinstance(obj, ResolutionAuditEvent):
                raise ResolutionAuditError(
                    "ResolutionAuditEvent rows are append-only; deletes are forbidden."
                )

    event.listen(Session, "before_flush", _protect)
    _AUDIT_LISTENER_REGISTERED = True
