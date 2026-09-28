"""Database readiness uses the application session dependency."""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.api.routes.health import readiness, router
from app.db.session import get_db
from app.main import app


class _FailingSession:
    def execute(self, *_args: object, **_kwargs: object) -> None:
        raise OperationalError(
            "SELECT 1",
            {},
            Exception("postgresql://user:secret-password@db.internal/reconai"),
        )


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_stays_a_liveness_check(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "reconai"}


def test_ready_uses_configured_database_dependency(client: TestClient) -> None:
    route = next(item for item in router.routes if getattr(item, "endpoint", None) is readiness)
    assert any(dep.call is get_db for dep in route.dependant.dependencies)
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_is_503_when_database_execute_fails() -> None:
    def _override() -> Generator[_FailingSession, None, None]:
        yield _FailingSession()

    app.dependency_overrides[get_db] = _override
    try:
        response = TestClient(app).get("/ready")
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    body = response.text
    assert response.json() == {"status": "not_ready"}
    assert "secret-password" not in body
    assert "db.internal" not in body
    assert "Traceback" not in body
    assert "postgresql://" not in body
