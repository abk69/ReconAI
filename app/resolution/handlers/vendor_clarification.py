"""REQUEST_VENDOR_CLARIFICATION — durable request record (no email)."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import Vendor, VendorClarificationRequest
from app.domain.enums import ActionType, WorkflowRequestStatus
from app.resolution.context import ActionExecutionContext
from app.resolution.contracts import (
    ActionParameters,
    ActionResult,
    RequestVendorClarificationParameters,
)
from app.resolution.registry import ActionHandler


class RequestVendorClarificationHandler(ActionHandler):
    action_type = ActionType.REQUEST_VENDOR_CLARIFICATION
    description = "Create a vendor clarification request for disputed fields."
    requires_approval = True

    def execute(
        self,
        parameters: ActionParameters,
        context: ActionExecutionContext,
    ) -> ActionResult:
        params = (
            parameters
            if isinstance(parameters, RequestVendorClarificationParameters)
            else RequestVendorClarificationParameters.model_validate(parameters.model_dump())
        )

        existing = context.session.scalar(
            select(VendorClarificationRequest).where(
                VendorClarificationRequest.proposed_action_id == context.action.id
            )
        )
        if existing is not None:
            return ActionResult(
                success=True,
                status="already_exists",
                reference_id=existing.id,
                message="Vendor clarification request already exists for this action.",
                data={
                    "vendor_clarification_request_id": str(existing.id),
                    "status": existing.status,
                },
            )

        if params.vendor_id is not None:
            vendor = context.session.get(Vendor, params.vendor_id)
            if vendor is None:
                raise ValueError(f"Vendor {params.vendor_id} was not found.")

        row = VendorClarificationRequest(
            reconciliation_exception_id=context.exception.id,
            proposed_action_id=context.action.id,
            vendor_id=params.vendor_id,
            vendor_reference=params.vendor_reference,
            question=params.question,
            reason=params.reason,
            fields=list(params.fields),
            due_date=params.due_date,
            status=WorkflowRequestStatus.PENDING.value,
        )
        context.session.add(row)
        context.session.flush()

        return ActionResult(
            success=True,
            status="created",
            reference_id=row.id,
            message="Vendor clarification request created (no external send).",
            data={
                "vendor_clarification_request_id": str(row.id),
                "reconciliation_exception_id": str(context.exception.id),
                "vendor_id": str(row.vendor_id) if row.vendor_id else None,
                "vendor_reference": row.vendor_reference,
                "status": row.status,
            },
        )
