"""Query resolution audit trails (M8.6)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ResolutionAuditEvent, ResolutionPlan
from app.domain.enums import ResolutionAuditActorType, ResolutionAuditEventType


class ResolutionAuditNotFoundError(Exception):
    """Plan or action audit scope not found."""


class ResolutionAuditService:
    """Read-only chronological audit queries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_plan_audit(self, plan_id: UUID) -> list[ResolutionAuditEvent]:
        plan = self._session.get(ResolutionPlan, plan_id)
        if plan is None:
            raise ResolutionAuditNotFoundError(f"Resolution plan {plan_id} was not found.")
        rows = self._session.scalars(
            select(ResolutionAuditEvent)
            .where(ResolutionAuditEvent.resolution_plan_id == plan_id)
            .order_by(ResolutionAuditEvent.created_at, ResolutionAuditEvent.id)
        ).all()
        return list(rows)

    def get_action_audit(self, action_id: UUID) -> list[ResolutionAuditEvent]:
        rows = self._session.scalars(
            select(ResolutionAuditEvent)
            .where(ResolutionAuditEvent.proposed_action_id == action_id)
            .order_by(ResolutionAuditEvent.created_at, ResolutionAuditEvent.id)
        ).all()
        if not rows:
            # Distinguish empty history vs unknown action via plan ownership elsewhere;
            # return empty list when no events (caller may 404 if action missing).
            return []
        return list(rows)

    @staticmethod
    def parse_event_type(value: str) -> ResolutionAuditEventType:
        return ResolutionAuditEventType(value)

    @staticmethod
    def parse_actor_type(value: str) -> ResolutionAuditActorType:
        return ResolutionAuditActorType(value)
