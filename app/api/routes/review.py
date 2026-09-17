"""Human review queue API routes (M5)."""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.enums import DocumentType, ReviewAction, ReviewPriority, ReviewStatus
from app.review.transitions import InvalidReviewTransitionError
from app.schemas.review import (
    PromoteResponse,
    ReviewApproveRequest,
    ReviewCorrectRequest,
    ReviewDecisionResponse,
    ReviewRejectRequest,
    ReviewTaskListResponse,
    ReviewTaskResponse,
)
from app.services.promotion_service import (
    PromotionError,
    PromotionNotAllowedError,
    PromotionService,
    PromotionValidationError,
)
from app.services.review_service import (
    ReviewNotFoundError,
    ReviewService,
    ReviewValidationError,
)

router = APIRouter(prefix="/review", tags=["review"])
DbSession = Annotated[Session, Depends(get_db)]


def _candidate_summary(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if not candidate:
        return None
    keys = (
        "invoice_number",
        "po_number",
        "grn_number",
        "vendor_name",
        "invoice_date",
        "order_date",
        "receipt_date",
        "currency",
        "total_amount",
    )
    summary = {k: candidate[k] for k in keys if k in candidate and candidate[k] is not None}
    lines = candidate.get("lines")
    if isinstance(lines, list):
        summary["line_count"] = len(lines)
    return summary


def _to_response(task: object) -> ReviewTaskResponse:
    document = getattr(task, "document", None)
    extraction = getattr(task, "extraction_result", None)
    original = extraction.candidate if extraction is not None else None
    reviewed = getattr(task, "reviewed_candidate", None)
    evidence = extraction.evidence if extraction is not None else []
    decisions = [
        ReviewDecisionResponse(
            id=d.id,
            action=ReviewAction(d.action),
            field_path=d.field_path,
            original_value=d.original_value,
            corrected_value=d.corrected_value,
            reason=d.reason,
            reviewer=d.reviewer,
            evidence_ref=d.evidence_ref,
            created_at=d.created_at,
        )
        for d in getattr(task, "decisions", []) or []
    ]
    doc_type = None
    if document is not None and document.document_type in DocumentType._value2member_map_:
        doc_type = DocumentType(document.document_type)
    detected = None
    if extraction is not None and extraction.detected_type in DocumentType._value2member_map_:
        detected = DocumentType(extraction.detected_type)

    return ReviewTaskResponse(
        id=task.id,  # type: ignore[attr-defined]
        document_id=task.document_id,  # type: ignore[attr-defined]
        extraction_result_id=task.extraction_result_id,  # type: ignore[attr-defined]
        status=ReviewStatus(task.status),  # type: ignore[attr-defined]
        reason=task.reason,  # type: ignore[attr-defined]
        priority=ReviewPriority(task.priority),  # type: ignore[attr-defined]
        assigned_to=task.assigned_to,  # type: ignore[attr-defined]
        document_type=doc_type,
        detected_type=detected,
        document_status=document.status if document is not None else None,
        candidate_summary=_candidate_summary(reviewed or original),
        reviewed_candidate=reviewed,
        original_candidate=original,
        evidence=evidence or [],
        decisions=decisions,
        promoted_entity_type=task.promoted_entity_type,  # type: ignore[attr-defined]
        promoted_entity_id=task.promoted_entity_id,  # type: ignore[attr-defined]
        promoted_at=task.promoted_at,  # type: ignore[attr-defined]
        created_at=task.created_at,  # type: ignore[attr-defined]
        updated_at=task.updated_at,  # type: ignore[attr-defined]
        completed_at=task.completed_at,  # type: ignore[attr-defined]
    )


@router.get("/tasks", response_model=ReviewTaskListResponse)
def list_review_tasks(
    session: DbSession,
    task_status: Annotated[ReviewStatus | None, Query(alias="status")] = None,
    document_type: DocumentType | None = None,
    priority: ReviewPriority | None = None,
) -> ReviewTaskListResponse:
    service = ReviewService(session)
    tasks = service.list_tasks(
        status=task_status,
        document_type=document_type,
        priority=priority,
    )
    items = [_to_response(t) for t in tasks]
    return ReviewTaskListResponse(items=items, count=len(items))


@router.get("/tasks/{task_id}", response_model=ReviewTaskResponse)
def get_review_task(task_id: UUID, session: DbSession) -> ReviewTaskResponse:
    service = ReviewService(session)
    try:
        task = service.get_task(task_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(task)


@router.post("/tasks/{task_id}/approve", response_model=ReviewTaskResponse)
def approve_review_task(
    task_id: UUID,
    body: ReviewApproveRequest,
    session: DbSession,
) -> ReviewTaskResponse:
    service = ReviewService(session)
    try:
        task = service.approve(task_id, reviewer=body.reviewer, reason=body.reason)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ReviewValidationError, InvalidReviewTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(task)


@router.post("/tasks/{task_id}/correct", response_model=ReviewTaskResponse)
def correct_review_task(
    task_id: UUID,
    body: ReviewCorrectRequest,
    session: DbSession,
) -> ReviewTaskResponse:
    service = ReviewService(session)
    corrections = [c.model_dump(mode="json") for c in body.corrections]
    try:
        task = service.correct(
            task_id,
            corrections=corrections,
            reviewer=body.reviewer,
            reason=body.reason,
        )
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ReviewValidationError, InvalidReviewTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(task)


@router.post("/tasks/{task_id}/reject", response_model=ReviewTaskResponse)
def reject_review_task(
    task_id: UUID,
    body: ReviewRejectRequest,
    session: DbSession,
) -> ReviewTaskResponse:
    service = ReviewService(session)
    try:
        task = service.reject(task_id, reviewer=body.reviewer, reason=body.reason)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ReviewValidationError, InvalidReviewTransitionError) as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    return _to_response(task)


@router.post("/tasks/{task_id}/promote", response_model=PromoteResponse)
def promote_review_task(task_id: UUID, session: DbSession) -> PromoteResponse:
    """Promote an APPROVED/CORRECTED candidate into authoritative PO/GRN/Invoice rows."""
    service = PromotionService(session)
    try:
        task = service.promote(task_id)
    except ReviewNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except PromotionNotAllowedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except PromotionValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except PromotionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    document = task.document
    return PromoteResponse(
        review_task_id=task.id,
        status=ReviewStatus(task.status),
        document_id=task.document_id,
        document_status=document.status if document is not None else "",
        promoted_entity_type=task.promoted_entity_type,
        promoted_entity_id=task.promoted_entity_id,
        promoted_at=task.promoted_at,
    )
