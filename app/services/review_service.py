"""Human review service — queue, transitions, audit trail (no HTTP)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Document, DocumentExtractionResult, ReviewDecision, ReviewTask
from app.domain.enums import (
    DocumentStatus,
    DocumentType,
    ExtractionOutcome,
    ReviewAction,
    ReviewPriority,
    ReviewStatus,
)
from app.review.candidate_ops import (
    CandidatePathError,
    deep_copy_candidate,
    get_field_value,
    serialize_value,
    set_field_value,
)
from app.review.transitions import (
    PROMOTABLE_STATUSES,
    InvalidReviewTransitionError,
    assert_transition,
)


class ReviewServiceError(Exception):
    """Base review service error."""


class ReviewNotFoundError(ReviewServiceError):
    """Review task not found."""


class ReviewValidationError(ReviewServiceError):
    """Invalid reviewer input or state."""


class ReviewService:
    """Create and advance review tasks for M4 extraction candidates."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create_review_task(
        self,
        *,
        document_id: UUID,
        extraction_result_id: UUID,
        reason: str | None = None,
        priority: ReviewPriority = ReviewPriority.MEDIUM,
        assigned_to: str | None = None,
        commit: bool = True,
    ) -> ReviewTask:
        """Idempotently create a review task for an extraction result.

        If a task already exists for ``extraction_result_id``, return it.
        """
        existing = self._session.scalar(
            select(ReviewTask).where(ReviewTask.extraction_result_id == extraction_result_id)
        )
        if existing is not None:
            return existing

        extraction = self._session.get(DocumentExtractionResult, extraction_result_id)
        if extraction is None:
            raise ReviewNotFoundError(f"Extraction result {extraction_result_id} was not found.")
        document = self._session.get(Document, document_id)
        if document is None:
            raise ReviewNotFoundError(f"Document {document_id} was not found.")
        if extraction.document_id != document_id:
            raise ReviewValidationError(
                "extraction_result_id does not belong to the given document_id."
            )

        task = ReviewTask(
            document_id=document_id,
            extraction_result_id=extraction_result_id,
            status=ReviewStatus.PENDING.value,
            reason=reason,
            priority=priority.value,
            assigned_to=assigned_to,
            reviewed_candidate=deep_copy_candidate(extraction.candidate),
        )
        self._session.add(task)
        if commit:
            self._session.commit()
            return self.get_task(task.id)
        self._session.flush()
        return task

    def create_from_extraction_if_needed(
        self,
        *,
        document: Document,
        extraction: DocumentExtractionResult,
        outcome: ExtractionOutcome,
        validation: dict | None = None,
    ) -> ReviewTask | None:
        """Create a review task when M4 outcome requires human intervention.

        Clean ``READY_FOR_RECONCILIATION`` results do not create tasks.
        """
        if outcome is not ExtractionOutcome.REVIEW_REQUIRED:
            return None

        priority = ReviewPriority.MEDIUM
        reason_parts: list[str] = []
        if extraction.message:
            reason_parts.append(extraction.message)
        if extraction.detected_type == DocumentType.UNKNOWN.value:
            priority = ReviewPriority.HIGH
            reason_parts.append("Document type is UNKNOWN.")
        validation = validation or extraction.validation or {}
        for issue in validation.get("issues") or []:
            code = issue.get("code") if isinstance(issue, dict) else None
            if code == "OCR_UNAVAILABLE":
                priority = ReviewPriority.HIGH
                reason_parts.append("OCR unavailable.")
            elif code == "UNKNOWN_OR_EMPTY":
                priority = ReviewPriority.HIGH

        reason = " ".join(reason_parts) if reason_parts else "Extraction requires human review."
        return self.create_review_task(
            document_id=document.id,
            extraction_result_id=extraction.id,
            reason=reason,
            priority=priority,
            commit=False,
        )

    def get_task(self, task_id: UUID) -> ReviewTask:
        task = self._session.scalar(
            select(ReviewTask)
            .where(ReviewTask.id == task_id)
            .options(
                selectinload(ReviewTask.decisions),
                selectinload(ReviewTask.extraction_result),
                selectinload(ReviewTask.document),
            )
        )
        if task is None:
            raise ReviewNotFoundError(f"Review task {task_id} was not found.")
        return task

    def list_tasks(
        self,
        *,
        status: ReviewStatus | None = None,
        document_type: DocumentType | None = None,
        priority: ReviewPriority | None = None,
    ) -> list[ReviewTask]:
        stmt = (
            select(ReviewTask)
            .join(Document, ReviewTask.document_id == Document.id)
            .options(
                selectinload(ReviewTask.decisions),
                selectinload(ReviewTask.extraction_result),
                selectinload(ReviewTask.document),
            )
            .order_by(ReviewTask.created_at.desc())
        )
        if status is not None:
            stmt = stmt.where(ReviewTask.status == status.value)
        if priority is not None:
            stmt = stmt.where(ReviewTask.priority == priority.value)
        if document_type is not None:
            stmt = stmt.where(Document.document_type == document_type.value)
        return list(self._session.scalars(stmt).unique().all())

    def start_review(
        self,
        task_id: UUID,
        *,
        reviewer: str | None = None,
    ) -> ReviewTask:
        task = self.get_task(task_id)
        current = ReviewStatus(task.status)
        assert_transition(current, ReviewStatus.IN_REVIEW)
        task.status = ReviewStatus.IN_REVIEW.value
        if reviewer:
            task.assigned_to = reviewer
        self._session.commit()
        return self.get_task(task_id)

    def approve(
        self,
        task_id: UUID,
        *,
        reviewer: str | None = None,
        reason: str | None = None,
    ) -> ReviewTask:
        task = self.get_task(task_id)
        current = ReviewStatus(task.status)
        if current is ReviewStatus.REJECTED:
            raise ReviewValidationError("Rejected review tasks cannot be approved.")
        if current is ReviewStatus.APPROVED:
            raise ReviewValidationError("Review task is already approved.")
        if current is ReviewStatus.PENDING:
            assert_transition(current, ReviewStatus.IN_REVIEW)
            task.status = ReviewStatus.IN_REVIEW.value
            current = ReviewStatus.IN_REVIEW
        assert_transition(current, ReviewStatus.APPROVED)

        if task.reviewed_candidate is None and task.extraction_result is not None:
            task.reviewed_candidate = deep_copy_candidate(task.extraction_result.candidate)

        decision = ReviewDecision(
            review_task_id=task.id,
            action=ReviewAction.APPROVE.value,
            reason=reason,
            reviewer=reviewer,
        )
        self._session.add(decision)
        task.status = ReviewStatus.APPROVED.value
        task.completed_at = datetime.now(UTC)
        if reviewer:
            task.assigned_to = reviewer
        self._session.commit()
        return self.get_task(task_id)

    def correct(
        self,
        task_id: UUID,
        *,
        corrections: list[dict[str, object]],
        reviewer: str | None = None,
        reason: str | None = None,
    ) -> ReviewTask:
        """Apply field corrections and transition to CORRECTED.

        Each correction dict: field_path, corrected_value, optional reason,
        optional evidence_ref.
        """
        if not corrections:
            raise ReviewValidationError("At least one field correction is required.")

        task = self.get_task(task_id)
        self._ensure_active(task)
        current = ReviewStatus(task.status)
        if current is ReviewStatus.PENDING:
            assert_transition(current, ReviewStatus.IN_REVIEW)
            task.status = ReviewStatus.IN_REVIEW.value
            current = ReviewStatus.IN_REVIEW
        assert_transition(current, ReviewStatus.CORRECTED)

        working = deep_copy_candidate(
            task.reviewed_candidate
            if task.reviewed_candidate is not None
            else (task.extraction_result.candidate if task.extraction_result is not None else None)
        )
        if working is None:
            raise ReviewValidationError("No candidate available to correct.")

        if (
            task.extraction_result is not None
            and task.extraction_result.document_id != task.document_id
        ):
            raise ReviewValidationError("Review task extraction result does not match document.")

        for item in corrections:
            field_path = str(item.get("field_path") or "").strip()
            if not field_path:
                raise ReviewValidationError("Each correction requires field_path.")
            if "corrected_value" not in item:
                raise ReviewValidationError(
                    f"Correction for {field_path} requires corrected_value."
                )
            try:
                original = get_field_value(working, field_path)
            except CandidatePathError as exc:
                raise ReviewValidationError(str(exc)) from exc
            try:
                set_field_value(working, field_path, item["corrected_value"])
                new_value = get_field_value(working, field_path)
            except CandidatePathError as exc:
                raise ReviewValidationError(str(exc)) from exc

            self._session.add(
                ReviewDecision(
                    review_task_id=task.id,
                    action=ReviewAction.CORRECT.value,
                    field_path=field_path,
                    original_value=serialize_value(original),
                    corrected_value=serialize_value(new_value),
                    reason=(str(item["reason"]) if item.get("reason") else reason),
                    reviewer=reviewer,
                    evidence_ref=(str(item["evidence_ref"]) if item.get("evidence_ref") else None),
                )
            )

        task.reviewed_candidate = working
        task.status = ReviewStatus.CORRECTED.value
        task.completed_at = datetime.now(UTC)
        if reason and not task.reason:
            task.reason = reason
        if reviewer:
            task.assigned_to = reviewer
        self._session.commit()
        return self.get_task(task_id)

    def reject(
        self,
        task_id: UUID,
        *,
        reviewer: str | None = None,
        reason: str | None = None,
    ) -> ReviewTask:
        task = self.get_task(task_id)
        self._ensure_active(task)
        current = ReviewStatus(task.status)
        if current is ReviewStatus.PENDING:
            assert_transition(current, ReviewStatus.IN_REVIEW)
            task.status = ReviewStatus.IN_REVIEW.value
            current = ReviewStatus.IN_REVIEW
        assert_transition(current, ReviewStatus.REJECTED)

        self._session.add(
            ReviewDecision(
                review_task_id=task.id,
                action=ReviewAction.REJECT.value,
                reason=reason,
                reviewer=reviewer,
            )
        )
        task.status = ReviewStatus.REJECTED.value
        task.completed_at = datetime.now(UTC)
        if reason:
            task.reason = reason
        if reviewer:
            task.assigned_to = reviewer

        document = self._session.get(Document, task.document_id)
        if document is not None:
            document.status = DocumentStatus.REVIEW_REJECTED.value

        self._session.commit()
        return self.get_task(task_id)

    def is_eligible_for_promotion(self, task: ReviewTask) -> bool:
        status = ReviewStatus(task.status)
        if status not in PROMOTABLE_STATUSES:
            return False
        candidate = task.reviewed_candidate
        if candidate is None and task.extraction_result is not None:
            candidate = task.extraction_result.candidate
        return candidate is not None

    def _ensure_active(self, task: ReviewTask) -> None:
        status = ReviewStatus(task.status)
        if status is ReviewStatus.REJECTED:
            raise ReviewValidationError("Rejected review tasks cannot be modified.")
        if status is ReviewStatus.APPROVED:
            raise ReviewValidationError("Approved review tasks cannot be modified.")
        if status is ReviewStatus.CORRECTED:
            # Allow approve after correct via separate transition only.
            raise ReviewValidationError(
                "Corrected review tasks are finalized; promote or leave as-is."
            )


# Re-export for callers
__all__ = [
    "InvalidReviewTransitionError",
    "ReviewNotFoundError",
    "ReviewService",
    "ReviewServiceError",
    "ReviewValidationError",
]
