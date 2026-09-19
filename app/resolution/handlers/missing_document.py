"""REQUEST_MISSING_DOCUMENT — durable request record (no external contact)."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import MissingDocumentRequest, Vendor
from app.domain.enums import ActionType, WorkflowRequestStatus
from app.resolution.context import ActionExecutionContext
from app.resolution.contracts import (
    ActionParameters,
    ActionResult,
    RequestMissingDocumentParameters,
)
from app.resolution.registry import ActionHandler


class RequestMissingDocumentHandler(ActionHandler):
    action_type = ActionType.REQUEST_MISSING_DOCUMENT
    description = "Create a missing-document workflow request."
    requires_approval = True

    def execute(
        self,
        parameters: ActionParameters,
        context: ActionExecutionContext,
    ) -> ActionResult:
        params = (
            parameters
            if isinstance(parameters, RequestMissingDocumentParameters)
            else RequestMissingDocumentParameters.model_validate(parameters.model_dump())
        )

        existing = context.session.scalar(
            select(MissingDocumentRequest).where(
                MissingDocumentRequest.proposed_action_id == context.action.id
            )
        )
        if existing is not None:
            return ActionResult(
                success=True,
                status="already_exists",
                reference_id=existing.id,
                message="Missing document request already exists for this action.",
                data={
                    "missing_document_request_id": str(existing.id),
                    "document_type": existing.document_type,
                    "status": existing.status,
                },
            )

        if params.vendor_id is not None:
            vendor = context.session.get(Vendor, params.vendor_id)
            if vendor is None:
                raise ValueError(f"Vendor {params.vendor_id} was not found.")

        row = MissingDocumentRequest(
            reconciliation_exception_id=context.exception.id,
            proposed_action_id=context.action.id,
            document_type=params.document_type,
            reason=params.reason,
            vendor_id=params.vendor_id,
            vendor_reference=params.vendor_reference,
            status=WorkflowRequestStatus.PENDING.value,
        )
        context.session.add(row)
        context.session.flush()

        return ActionResult(
            success=True,
            status="created",
            reference_id=row.id,
            message=f"Missing document request created for type '{params.document_type}'.",
            data={
                "missing_document_request_id": str(row.id),
                "document_type": row.document_type,
                "reconciliation_exception_id": str(context.exception.id),
                "status": row.status,
            },
        )
