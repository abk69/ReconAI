"""Bounded, resumable anomaly batch scanner (M9.2).

Batch semantics
---------------
Each batch:
  1. load entity IDs after checkpoint (deterministic UUID order)
  2. run existing AnomalyEngine rules via AnomalyService
  3. persist signals idempotently (fingerprint upsert)
  4. advance checkpoint + counters
  5. commit the batch

Isolated rule/entity failures increment ``error_count`` and continue.
A database transaction failure rolls the batch back, preserves the prior
checkpoint, and marks the job FAILED (resume continues from that checkpoint).

Scan-key idempotency
--------------------
When ``scan_key`` is supplied, ``(scan_type, scan_key)`` is unique. Creating
again returns the existing job (any status). Concurrent FULL scans without a
key are allowed as separate jobs; callers should supply a key for daily runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.anomaly.enums import AnomalyScanStatus, AnomalyScanType
from app.core.config import Settings, get_settings
from app.db.models import AnomalyScanJob, Invoice, ReconciliationException, Vendor
from app.services.anomaly_service import AnomalyService, config_from_settings


class AnomalyScanError(Exception):
    """Scan job domain / validation error."""


class AnomalyScanNotFoundError(AnomalyScanError):
    """Scan job missing."""


class AnomalyScanConflictError(AnomalyScanError):
    """Invalid status transition or concurrent-run conflict."""


_ACTIVE = frozenset({AnomalyScanStatus.PENDING.value, AnomalyScanStatus.RUNNING.value})
_TERMINAL = frozenset(
    {
        AnomalyScanStatus.COMPLETED.value,
        AnomalyScanStatus.FAILED.value,
        AnomalyScanStatus.CANCELLED.value,
    }
)


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_cursor(raw: str | None) -> tuple[str | None, UUID | None]:
    """Return (phase, entity_id). Phase is invoice|vendor|exception for FULL."""
    if not raw:
        return None, None
    if ":" in raw:
        phase, _, rest = raw.partition(":")
        if rest in {"", "DONE"}:
            return phase, None
        return phase, UUID(rest)
    return None, UUID(raw)


def _format_cursor(phase: str | None, entity_id: UUID | None, *, done: bool = False) -> str:
    if phase:
        if done:
            return f"{phase}:DONE"
        assert entity_id is not None
        return f"{phase}:{entity_id}"
    assert entity_id is not None
    return str(entity_id)


class AnomalyScanService:
    """Create, run, resume, and cancel bounded anomaly scan jobs."""

    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._batch_size = batch_size or self._settings.anomaly_scan_batch_size
        self._anomaly = AnomalyService(
            session, config=config_from_settings(self._settings)
        )

    def create_scan(
        self,
        *,
        scan_type: AnomalyScanType | str,
        scan_key: str | None = None,
        commit: bool = True,
    ) -> tuple[AnomalyScanJob, bool]:
        try:
            stype = AnomalyScanType(scan_type)
        except ValueError as exc:
            raise AnomalyScanError(
                f"Invalid scan_type {scan_type!r}; allowed: "
                f"{', '.join(t.value for t in AnomalyScanType)}"
            ) from exc

        key = scan_key.strip() if scan_key else None
        if key == "":
            key = None

        if key is not None:
            existing = self._session.scalar(
                select(AnomalyScanJob).where(
                    AnomalyScanJob.scan_type == stype.value,
                    AnomalyScanJob.scan_key == key,
                )
            )
            if existing is not None:
                return existing, True

        job = AnomalyScanJob(
            scan_type=stype.value,
            status=AnomalyScanStatus.PENDING.value,
            scan_key=key,
            requested_at=_now(),
            processed_count=0,
            anomaly_count=0,
            error_count=0,
        )
        self._session.add(job)
        self._session.flush()
        if commit:
            self._session.commit()
            self._session.refresh(job)
        return job, False

    def get_scan(self, scan_id: UUID) -> AnomalyScanJob:
        job = self._session.get(AnomalyScanJob, scan_id)
        if job is None:
            raise AnomalyScanNotFoundError(f"Scan job {scan_id} not found")
        return job

    def cancel_scan(self, scan_id: UUID, *, commit: bool = True) -> AnomalyScanJob:
        job = self.get_scan(scan_id)
        if job.status in {
            AnomalyScanStatus.COMPLETED.value,
            AnomalyScanStatus.CANCELLED.value,
        }:
            raise AnomalyScanConflictError(
                f"Cannot cancel scan in status {job.status}"
            )
        # FAILED can be cancelled to freeze further resume, or leave FAILED.
        if job.status == AnomalyScanStatus.FAILED.value:
            raise AnomalyScanConflictError(
                "Failed scans cannot be cancelled; use resume_scan or create a new job."
            )
        job.status = AnomalyScanStatus.CANCELLED.value
        job.completed_at = _now()
        job.updated_at = _now()
        # Preserve checkpoint + signals.
        self._session.flush()
        if commit:
            self._session.commit()
            self._session.refresh(job)
        return job

    def resume_scan(self, scan_id: UUID, *, commit: bool = True) -> AnomalyScanJob:
        """Resume a FAILED scan from its preserved checkpoint."""
        job = self.get_scan(scan_id)
        if job.status != AnomalyScanStatus.FAILED.value:
            raise AnomalyScanConflictError(
                f"Only FAILED scans can be resumed (status={job.status})"
            )
        job.status = AnomalyScanStatus.PENDING.value
        job.error_message = None
        job.completed_at = None
        job.updated_at = _now()
        self._session.flush()
        if commit:
            self._session.commit()
            self._session.refresh(job)
        return self.run_scan(scan_id, commit=commit)

    def run_scan(self, scan_id: UUID, *, commit: bool = True) -> AnomalyScanJob:
        """Execute scan batches until complete, cancelled, or failed."""
        job = self.get_scan(scan_id)
        if job.status == AnomalyScanStatus.CANCELLED.value:
            raise AnomalyScanConflictError("Cannot run a CANCELLED scan")
        if job.status == AnomalyScanStatus.COMPLETED.value:
            return job
        if job.status == AnomalyScanStatus.FAILED.value:
            raise AnomalyScanConflictError(
                "FAILED scan must be resumed via resume_scan"
            )
        if job.status not in _ACTIVE:
            raise AnomalyScanConflictError(f"Cannot run scan in status {job.status}")

        job.status = AnomalyScanStatus.RUNNING.value
        if job.started_at is None:
            job.started_at = _now()
        job.updated_at = _now()
        self._session.flush()
        if commit:
            self._session.commit()

        try:
            stype = AnomalyScanType(job.scan_type)
            if stype is AnomalyScanType.INVOICE:
                self._run_entity_scan(job, entity="invoice", commit=commit)
            elif stype is AnomalyScanType.VENDOR:
                self._run_entity_scan(job, entity="vendor", commit=commit)
            elif stype is AnomalyScanType.EXCEPTION:
                self._run_entity_scan(job, entity="exception", commit=commit)
            else:
                self._run_full_scan(job, commit=commit)
        except AnomalyScanConflictError:
            raise
        except SQLAlchemyError as exc:
            self._session.rollback()
            job = self.get_scan(scan_id)
            job.status = AnomalyScanStatus.FAILED.value
            job.error_message = f"Database transaction failed: {exc.__class__.__name__}"
            job.completed_at = _now()
            job.updated_at = _now()
            self._session.flush()
            if commit:
                self._session.commit()
                self._session.refresh(job)
            return job

        job = self.get_scan(scan_id)
        if job.status == AnomalyScanStatus.RUNNING.value:
            job.status = AnomalyScanStatus.COMPLETED.value
            job.completed_at = _now()
            job.updated_at = _now()
            job.error_message = None
            self._session.flush()
            if commit:
                self._session.commit()
                self._session.refresh(job)
        return job

    def _refresh_cancelled(self, job: AnomalyScanJob) -> bool:
        self._session.refresh(job)
        return job.status == AnomalyScanStatus.CANCELLED.value

    def _run_entity_scan(
        self, job: AnomalyScanJob, *, entity: str, commit: bool
    ) -> None:
        phase = None  # simple scans store bare UUID cursor
        while True:
            if self._refresh_cancelled(job):
                return
            _, after_id = _parse_cursor(job.last_cursor)
            batch_ids = self._fetch_batch_ids(entity, after_id=after_id)
            if not batch_ids:
                return
            self._process_batch(job, entity=entity, ids=batch_ids, phase=phase, commit=commit)

    def _run_full_scan(self, job: AnomalyScanJob, *, commit: bool) -> None:
        """FULL = invoice phase then vendor phase (phased cursors)."""
        phase, after_id = self._full_phase_state(job.last_cursor)

        if phase == "invoice":
            while True:
                if self._refresh_cancelled(job):
                    return
                _, after_id = self._full_phase_state(job.last_cursor)
                if job.last_cursor and job.last_cursor.startswith("invoice:DONE"):
                    break
                if job.last_cursor and job.last_cursor.startswith("vendor:"):
                    break
                batch_ids = self._fetch_batch_ids("invoice", after_id=after_id)
                if not batch_ids:
                    job.last_cursor = "invoice:DONE"
                    job.updated_at = _now()
                    self._session.flush()
                    if commit:
                        self._session.commit()
                    break
                self._process_batch(
                    job, entity="invoice", ids=batch_ids, phase="invoice", commit=commit
                )

        if self._refresh_cancelled(job):
            return

        while True:
            if self._refresh_cancelled(job):
                return
            phase, after_id = self._full_phase_state(job.last_cursor)
            if phase == "vendor" and job.last_cursor == "vendor:DONE":
                return
            if phase != "vendor":
                after_id = None
            batch_ids = self._fetch_batch_ids("vendor", after_id=after_id)
            if not batch_ids:
                job.last_cursor = "vendor:DONE"
                job.updated_at = _now()
                self._session.flush()
                if commit:
                    self._session.commit()
                return
            self._process_batch(
                job, entity="vendor", ids=batch_ids, phase="vendor", commit=commit
            )

    @staticmethod
    def _full_phase_state(cursor: str | None) -> tuple[str, UUID | None]:
        if not cursor:
            return "invoice", None
        if cursor == "invoice:DONE":
            return "vendor", None
        if cursor == "vendor:DONE":
            return "vendor", None
        phase, entity_id = _parse_cursor(cursor)
        if phase in {"invoice", "vendor"}:
            return phase, entity_id
        # Bare UUID mid-invoice scan
        return "invoice", UUID(cursor) if cursor else None

    def _fetch_batch_ids(
        self, entity: str, *, after_id: UUID | None
    ) -> list[UUID]:
        if entity == "invoice":
            id_col = Invoice.id
        elif entity == "vendor":
            id_col = Vendor.id
        elif entity == "exception":
            id_col = ReconciliationException.id
        else:
            raise AnomalyScanError(f"Unknown entity {entity}")

        stmt = select(id_col).order_by(id_col.asc()).limit(self._batch_size)
        if after_id is not None:
            stmt = stmt.where(id_col > after_id)
        return list(self._session.scalars(stmt).all())

    def _process_batch(
        self,
        job: AnomalyScanJob,
        *,
        entity: str,
        ids: list[UUID],
        phase: str | None,
        commit: bool,
    ) -> None:
        new_anomalies = 0
        errors = 0
        last_id: UUID | None = None
        try:
            for entity_id in ids:
                if self._refresh_cancelled(job):
                    return
                try:
                    before_fps = self._fingerprint_snapshot_for_detect(entity, entity_id)
                    rows = self._detect_entity(entity, entity_id)
                    after_fps = {r.fingerprint for r in rows}
                    # Count newly created fingerprints in this pass.
                    created = after_fps - before_fps
                    # Also count reused hits toward anomaly_count as "signals found".
                    new_anomalies += len(rows)
                    _ = created  # fingerprints remain idempotent across resume
                except Exception as exc:  # noqa: BLE001 — isolated entity failure
                    errors += 1
                    # Keep last safe message (no stack trace).
                    job.error_message = (
                        f"Isolated {entity} error on {entity_id}: {exc.__class__.__name__}"
                    )[:2000]
                last_id = entity_id

            if last_id is None:
                return
            job.last_cursor = _format_cursor(phase, last_id)
            job.processed_count += len(ids)
            job.anomaly_count += new_anomalies
            job.error_count += errors
            job.updated_at = _now()
            self._session.flush()
            if commit:
                self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            raise

    def _fingerprint_snapshot_for_detect(self, entity: str, entity_id: UUID) -> set[str]:
        # Lightweight: empty set — anomaly_count counts signals returned per entity.
        return set()

    def _detect_entity(self, entity: str, entity_id: UUID):
        if entity == "invoice":
            return self._anomaly.detect_for_invoice(entity_id, commit=False)
        if entity == "vendor":
            return self._anomaly.detect_for_vendor(entity_id, commit=False)
        if entity == "exception":
            return self._anomaly.detect_for_exception(entity_id, commit=False)
        raise AnomalyScanError(f"Unknown entity {entity}")
