"""Worker poll health. A stopped worker must not be reported as healthy."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import WorkerHeartbeat
from app.db.session import get_db
from app.main import app
from app.workers.health import STALE_AFTER, assess_worker, record_poll


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def test_worker_is_unavailable_until_it_polls(client: TestClient) -> None:
    response = client.get("/health/worker")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "last_poll_at": None}


def test_idle_worker_is_healthy(client: TestClient, db_session: Session) -> None:
    record_poll(db_session, "idle-worker")
    response = client.get("/health/worker")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["last_poll_at"] is not None


def test_stopped_worker_is_stale_not_healthy(client: TestClient, db_session: Session) -> None:
    record_poll(db_session, "stopped-worker")
    assert client.get("/health/worker").status_code == 200

    row = db_session.get(WorkerHeartbeat, "stopped-worker")
    assert row is not None
    row.last_poll_at = datetime.now(UTC) - STALE_AFTER - timedelta(seconds=1)
    db_session.commit()

    response = client.get("/health/worker")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "stale"
    assert body["status"] != "healthy"
    assert body["last_poll_at"] is not None


def test_fresh_poll_keeps_an_older_worker_from_marking_the_pool_stale(
    db_session: Session,
) -> None:
    record_poll(db_session, "old-worker", at=datetime.now(UTC) - timedelta(minutes=10))
    record_poll(db_session, "live-worker")
    assert assess_worker(db_session).status == "healthy"
