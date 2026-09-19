"""ESCALATE_TO_MANAGER — durable escalation record (no notification)."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import ManagerEscalation
from app.domain.enums import ActionType, EscalationStatus
from app.resolution.context import ActionExecutionContext
from app.resolution.contracts import (
    ActionParameters,
    ActionResult,
    EscalateToManagerParameters,
)
from app.resolution.registry import ActionHandler


class EscalateToManagerHandler(ActionHandler):
    action_type = ActionType.ESCALATE_TO_MANAGER
    description = "Escalate a reconciliation exception to a manager or team."
    requires_approval = True

    def execute(
        self,
        parameters: ActionParameters,
        context: ActionExecutionContext,
    ) -> ActionResult:
        params = (
            parameters
            if isinstance(parameters, EscalateToManagerParameters)
            else EscalateToManagerParameters.model_validate(parameters.model_dump())
        )

        existing = context.session.scalar(
            select(ManagerEscalation).where(
                ManagerEscalation.proposed_action_id == context.action.id
            )
        )
        if existing is not None:
            return ActionResult(
                success=True,
                status="already_exists",
                reference_id=existing.id,
                message="Manager escalation already exists for this action.",
                data={
                    "manager_escalation_id": str(existing.id),
                    "priority": existing.priority,
                    "status": existing.status,
                },
            )

        row = ManagerEscalation(
            reconciliation_exception_id=context.exception.id,
            proposed_action_id=context.action.id,
            reason=params.reason,
            priority=params.priority.value,
            destination=params.destination,
            status=EscalationStatus.OPEN.value,
        )
        context.session.add(row)
        context.session.flush()

        return ActionResult(
            success=True,
            status="created",
            reference_id=row.id,
            message="Manager escalation created (no notification sent).",
            data={
                "manager_escalation_id": str(row.id),
                "priority": row.priority,
                "destination": row.destination,
                "reconciliation_exception_id": str(context.exception.id),
                "status": row.status,
            },
        )
