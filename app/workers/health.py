"""Worker liveness from the last successful queue poll.

An idle worker still polls, so a recent timestamp is healthy. A process that
has stopped leaves the old timestamp in place. No row means no worker has
polled this database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import WorkerHeartbeat

STALE_AFTER = timedelta(seconds=20)
HEARTBEAT_INTERVAL = timedelta(seconds=5)


@dataclass(frozen=True)
class WorkerHealth:
    status: str
    last_poll_at: datetime | None


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def record_poll(session: Session, worker_id: str, *, at: datetime | None = None) -> None:
    """Store a successful poll. Callers use their own session."""
    moment = at or datetime.now(UTC)
    row = session.get(WorkerHeartbeat, worker_id)
    if row is None:
        session.add(WorkerHeartbeat(worker_id=worker_id, last_poll_at=moment))
    else:
        row.last_poll_at = moment
    session.commit()


def assess_worker(session: Session, *, now: datetime | None = None) -> WorkerHealth:
    """Return healthy, stale, or unavailable from recorded polls."""
    moment = now or datetime.now(UTC)
    rows = list(session.scalars(select(WorkerHeartbeat)))
    if not rows:
        return WorkerHealth(status="unavailable", last_poll_at=None)
    latest = max(rows, key=lambda row: _aware(row.last_poll_at))
    last_poll_at = _aware(latest.last_poll_at)
    if moment - last_poll_at <= STALE_AFTER:
        return WorkerHealth(status="healthy", last_poll_at=last_poll_at)
    return WorkerHealth(status="stale", last_poll_at=last_poll_at)
