"""Execution context passed to registered action handlers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.models import ProposedAction, ReconciliationException, ResolutionPlan


@dataclass(frozen=True)
class ActionExecutionContext:
    """Deterministic runtime context for a single action execution."""

    session: Session
    plan: ResolutionPlan
    action: ProposedAction
    exception: ReconciliationException
    idempotency_key: str
