"""Run persisted jobs outside the HTTP request. One claim, then the work."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import ProcessingJob
from app.db.tenant_filter import reset_tenant_id, set_tenant_id
from app.domain.enums import JobType
from app.services.document_understanding_service import (
    DocumentUnderstandingNotFoundError,
    DocumentUnderstandingService,
)
from app.services.job_service import JobService
from app.services.llm_understanding_service import (
    LlmUnderstandingNotFoundError,
    LlmUnderstandingService,
)
from app.storage.base import StorageError
from app.storage.local import LocalFileStorage

logger = logging.getLogger("reconai.jobs")


class PermanentJobError(Exception):
    """A failure that must not be retried automatically."""


_PERMANENT = (
    DocumentUnderstandingNotFoundError,
    LlmUnderstandingNotFoundError,
    StorageError,
    PermanentJobError,
)


def run_available(session: Session, *, worker_id: str, limit: int = 1) -> int:
    """Claim and finish up to ``limit`` jobs. Returns how many were claimed."""
    service = JobService(session)
    finished = 0
    for _ in range(limit):
        job = service.claim(worker_id)
        if job is None:
            break
        _execute(session, job)
        finished += 1
    return finished


def _execute(session: Session, job: ProcessingJob) -> None:
    tenant_id = job.tenant_id
    # Drop instances loaded for a previous job before this tenant is bound.
    session.expire_all()
    token = set_tenant_id(tenant_id)
    logger.info(
        "job_start id=%s type=%s correlation_id=%s attempt=%s",
        job.id,
        job.job_type,
        job.correlation_id or "-",
        job.attempt_count,
    )
    try:
        _dispatch(session, job)
    except _PERMANENT as exc:
        JobService(session).mark_failed(
            job.id, code=exc.__class__.__name__, message=str(exc), permanent=True
        )
        logger.info("job_failed id=%s category=permanent code=%s", job.id, exc.__class__.__name__)
    except Exception as exc:
        logger.error("job_failed id=%s category=transient code=%s", job.id, type(exc).__name__)
        JobService(session).mark_failed(
            job.id, code="worker_error", message="The job could not be completed.", permanent=False
        )
    else:
        JobService(session).mark_succeeded(job.id)
        logger.info("job_succeeded id=%s correlation_id=%s", job.id, job.correlation_id or "-")
    finally:
        reset_tenant_id(token)


def _dispatch(session: Session, job: ProcessingJob) -> None:
    resource_id = job.resource_id
    if not isinstance(resource_id, uuid.UUID):
        resource_id = uuid.UUID(str(resource_id))
    if job.job_type == JobType.DOCUMENT_UNDERSTAND.value:
        settings = get_settings()
        DocumentUnderstandingService(
            session, storage=LocalFileStorage(settings.storage_root)
        ).understand(resource_id)
        return
    if job.job_type == JobType.LLM_UNDERSTAND.value:
        LlmUnderstandingService(session).understand(resource_id)
        return
    raise PermanentJobError("unknown_job_type")
