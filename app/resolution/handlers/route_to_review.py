"""ROUTE_TO_REVIEW — create exception review route (+ optional M5 ReviewTask)."""

from __future__ import annotations

from sqlalchemy import select

from app.db.models import ExceptionReviewRoute
from app.domain.enums import ActionType, ExceptionReviewRouteStatus, ReviewPriority
from app.resolution.context import ActionExecutionContext
from app.resolution.contracts import (
    ActionParameters,
    ActionResult,
    RouteToReviewParameters,
)
from app.resolution.registry import ActionHandler
from app.services.review_service import ReviewService


class RouteToReviewHandler(ActionHandler):
    action_type = ActionType.ROUTE_TO_REVIEW
    description = "Route a reconciliation exception to a human review queue."
    requires_approval = True

    def execute(
        self,
        parameters: ActionParameters,
        context: ActionExecutionContext,
    ) -> ActionResult:
        params = parameters if isinstance(parameters, RouteToReviewParameters) else (
            RouteToReviewParameters.model_validate(parameters.model_dump())
        )

        existing = context.session.scalar(
            select(ExceptionReviewRoute).where(
                ExceptionReviewRoute.proposed_action_id == context.action.id
            )
        )
        if existing is not None:
            return ActionResult(
                success=True,
                status="already_exists",
                reference_id=existing.id,
                message="Exception review route already exists for this action.",
                data={
                    "exception_review_route_id": str(existing.id),
                    "review_task_id": (
                        str(existing.review_task_id) if existing.review_task_id else None
                    ),
                    "review_queue": existing.review_queue,
                    "status": existing.status,
                },
            )

        review_task_id = None
        if params.document_id is not None and params.extraction_result_id is not None:
            review = ReviewService(context.session)
            task = review.create_review_task(
                document_id=params.document_id,
                extraction_result_id=params.extraction_result_id,
                reason=params.reason
                or f"Routed from resolution plan for exception {context.exception.id}",
                priority=ReviewPriority.MEDIUM,
                assigned_to=params.assigned_to,
                commit=False,
            )
            review_task_id = task.id

        route = ExceptionReviewRoute(
            reconciliation_exception_id=context.exception.id,
            proposed_action_id=context.action.id,
            review_queue=params.review_queue,
            reason=params.reason,
            assigned_to=params.assigned_to,
            review_task_id=review_task_id,
            status=ExceptionReviewRouteStatus.PENDING.value,
        )
        context.session.add(route)
        context.session.flush()

        return ActionResult(
            success=True,
            status="created",
            reference_id=route.id,
            message=f"Routed exception to review queue '{params.review_queue}'.",
            data={
                "exception_review_route_id": str(route.id),
                "review_task_id": str(review_task_id) if review_task_id else None,
                "review_queue": route.review_queue,
                "reconciliation_exception_id": str(context.exception.id),
                "status": route.status,
            },
        )
