"""Job status. Reading a job does not run it."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict

from app.api.deps import DbSession
from app.domain.enums import JobType
from app.services.job_service import JobNotFoundError, JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    job_type: str
    status: str
    resource_type: str
    resource_id: UUID
    attempt_count: int
    error_category: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    correlation_id: str | None = None
    reused_existing: bool = False


class JobQueueResponse(BaseModel):
    counts: dict[str, int]


def _to_response(row: object, *, reused: bool = False) -> JobResponse:
    return JobResponse(
        id=row.id,  # type: ignore[attr-defined]
        job_type=row.job_type,  # type: ignore[attr-defined]
        status=row.status,  # type: ignore[attr-defined]
        resource_type=row.resource_type,  # type: ignore[attr-defined]
        resource_id=row.resource_id,  # type: ignore[attr-defined]
        attempt_count=row.attempt_count,  # type: ignore[attr-defined]
        error_category=row.error_category,  # type: ignore[attr-defined]
        error_code=row.error_code,  # type: ignore[attr-defined]
        error_message=row.error_message,  # type: ignore[attr-defined]
        correlation_id=row.correlation_id,  # type: ignore[attr-defined]
        reused_existing=reused,
    )


@router.get("", response_model=JobQueueResponse)
def queue_depth(session: DbSession) -> JobQueueResponse:
    return JobQueueResponse(counts=JobService(session).counts())


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, session: DbSession) -> JobResponse:
    try:
        return _to_response(JobService(session).get(job_id))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: UUID, session: DbSession) -> JobResponse:
    try:
        return _to_response(JobService(session).retry(job_id))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: UUID, session: DbSession) -> JobResponse:
    try:
        return _to_response(JobService(session).cancel(job_id))
    except JobNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


def enqueue_document_job(session: DbSession, document_id: UUID, job_type: JobType) -> JobResponse:
    row, reused = JobService(session).enqueue(
        job_type=job_type,
        resource_type="document",
        resource_id=document_id,
    )
    return _to_response(row, reused=reused)
