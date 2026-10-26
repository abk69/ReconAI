"""Persist and claim background jobs. Acceptance means the row committed."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.request_context import current_request_id
from app.core.safe_text import sanitize_public_message
from app.db.models import ProcessingJob
from app.db.tenant_filter import current_tenant_id, set_tenant_id, suspend_tenant_filter
from app.domain.enums import JobStatus, JobType

_ACTIVE = {
    JobStatus.QUEUED.value,
    JobStatus.RUNNING.value,
    JobStatus.RETRY_SCHEDULED.value,
}
_LEASE = timedelta(minutes=5)
_BACKOFF_SECONDS = (5, 20, 60)


class JobNotFoundError(Exception):
    pass


class JobService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def enqueue(
        self,
        *,
        job_type: JobType,
        resource_type: str,
        resource_id: uuid.UUID,
    ) -> tuple[ProcessingJob, bool]:
        tenant_id = current_tenant_id()
        if tenant_id is None:
            raise RuntimeError("A tenant is required before queueing work.")
        key = f"{job_type.value}:{resource_id}"
        existing = self._session.scalar(
            select(ProcessingJob).where(
                ProcessingJob.idempotency_key == key,
                ProcessingJob.status.in_(_ACTIVE),
            )
        )
        if existing is not None:
            return existing, True
        now = datetime.now(UTC)
        row = ProcessingJob(
            job_type=job_type.value,
            status=JobStatus.QUEUED.value,
            resource_type=resource_type,
            resource_id=resource_id,
            idempotency_key=key,
            attempt_count=0,
            max_attempts=3,
            run_after=now,
            correlation_id=current_request_id(),
        )
        self._session.add(row)
        self._session.commit()
        return row, False

    def get(self, job_id: uuid.UUID) -> ProcessingJob:
        row = self._session.get(ProcessingJob, job_id)
        if row is None:
            raise JobNotFoundError("Job not found.")
        return row

    def retry(self, job_id: uuid.UUID) -> ProcessingJob:
        row = self.get(job_id)
        if row.status != JobStatus.FAILED.value:
            return row
        row.status = JobStatus.QUEUED.value
        row.run_after = datetime.now(UTC)
        row.finished_at = None
        row.error_category = None
        row.error_code = None
        row.error_message = None
        row.leased_until = None
        row.leased_by = None
        self._session.commit()
        return row

    def cancel(self, job_id: uuid.UUID) -> ProcessingJob:
        row = self.get(job_id)
        if row.status in {JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value}:
            row.status = JobStatus.CANCELLED.value
            row.finished_at = datetime.now(UTC)
            self._session.commit()
        return row

    def claim(self, worker_id: str) -> ProcessingJob | None:
        self.recover_expired_leases()
        now = datetime.now(UTC)
        with suspend_tenant_filter():
            stmt = (
                select(ProcessingJob)
                .where(
                    ProcessingJob.status.in_(
                        [JobStatus.QUEUED.value, JobStatus.RETRY_SCHEDULED.value]
                    )
                )
                .where(ProcessingJob.run_after <= now)
                .order_by(ProcessingJob.created_at)
                .limit(1)
            )
            bind = self._session.get_bind()
            if bind is not None and bind.dialect.name == "postgresql":
                stmt = stmt.with_for_update(skip_locked=True)
            candidate = self._session.scalar(stmt)
            if candidate is None:
                return None
            previous = candidate.status
            result = self._session.execute(
                update(ProcessingJob)
                .where(ProcessingJob.id == candidate.id, ProcessingJob.status == previous)
                .values(
                    status=JobStatus.RUNNING.value,
                    attempt_count=ProcessingJob.attempt_count + 1,
                    leased_until=now + _LEASE,
                    leased_by=worker_id,
                    started_at=now,
                )
            )
            if result.rowcount != 1:
                self._session.rollback()
                return None
            self._session.commit()
            self._session.refresh(candidate)
            return candidate

    def recover_expired_leases(self) -> int:
        now = datetime.now(UTC)
        with suspend_tenant_filter():
            expired = list(
                self._session.scalars(
                    select(ProcessingJob).where(
                        ProcessingJob.status == JobStatus.RUNNING.value,
                        ProcessingJob.leased_until.is_not(None),
                        ProcessingJob.leased_until < now,
                    )
                )
            )
            for row in expired:
                self._fail_or_retry(
                    row, code="lease_expired", message="The worker stopped before finishing."
                )
            if expired:
                self._session.commit()
            return len(expired)

    def mark_succeeded(self, job_id: uuid.UUID) -> None:
        with suspend_tenant_filter():
            row = self._session.get(ProcessingJob, job_id)
            if row is None:
                return
            row.status = JobStatus.SUCCEEDED.value
            row.finished_at = datetime.now(UTC)
            row.leased_until = None
            row.error_category = None
            row.error_code = None
            row.error_message = None
            self._session.commit()

    def mark_failed(self, job_id: uuid.UUID, *, code: str, message: str, permanent: bool) -> None:
        with suspend_tenant_filter():
            row = self._session.get(ProcessingJob, job_id)
            if row is None:
                return
            if permanent:
                row.status = JobStatus.FAILED.value
                row.error_category = "permanent"
                row.finished_at = datetime.now(UTC)
                row.leased_until = None
                row.error_code = code[:64]
                row.error_message = sanitize_public_message(message, fallback="The job failed.")
            else:
                self._fail_or_retry(row, code=code, message=message)
            self._session.commit()

    def counts(self) -> dict[str, int]:
        from sqlalchemy import func

        grouped = self._session.execute(
            select(ProcessingJob.status, func.count()).group_by(ProcessingJob.status)
        ).all()
        return {status: int(count) for status, count in grouped}

    def _fail_or_retry(self, row: ProcessingJob, *, code: str, message: str) -> None:
        safe = sanitize_public_message(message, fallback="The job failed.")
        row.error_code = code[:64]
        row.error_message = safe
        row.leased_until = None
        row.leased_by = None
        if row.attempt_count >= row.max_attempts:
            row.status = JobStatus.FAILED.value
            row.error_category = "transient"
            row.finished_at = datetime.now(UTC)
            return
        delay = _BACKOFF_SECONDS[min(row.attempt_count, len(_BACKOFF_SECONDS)) - 1]
        row.status = JobStatus.RETRY_SCHEDULED.value
        row.error_category = "transient"
        row.run_after = datetime.now(UTC) + timedelta(seconds=delay)
        row.finished_at = None


def bind_job_tenant(job: ProcessingJob):
    return set_tenant_id(job.tenant_id)
