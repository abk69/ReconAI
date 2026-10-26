"""PostgreSQL job claims. These tests do not run on SQLite."""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
from app.db.models import ProcessingJob, Tenant
from app.db.session import get_engine, get_session_factory
from app.db.tenant_filter import reset_tenant_id, set_tenant_id
from app.domain.enums import JobStatus, JobType
from app.services.job_service import JobService

pytestmark = pytest.mark.postgres

_SIDE_DB = "reconai_v15_worker_check"


def _require_postgres_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith("postgresql") or ":5433/" not in url:
        pytest.skip("DATABASE_URL is not the isolated PostgreSQL instance on port 5433")
    return url


@pytest.fixture
def postgres_factory() -> Iterator[sessionmaker[Session]]:
    """Migrate a throwaway database on the isolated instance and drop it afterward."""
    base = _require_postgres_url()
    admin_url = base.rsplit("/", 1)[0] + "/postgres"
    side_url = base.rsplit("/", 1)[0] + f"/{_SIDE_DB}"
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(
            text(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = :name AND pid <> pg_backend_pid()"
            ),
            {"name": _SIDE_DB},
        )
        connection.execute(text(f"DROP DATABASE IF EXISTS {_SIDE_DB}"))
        connection.execute(text(f"CREATE DATABASE {_SIDE_DB}"))
    admin.dispose()

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = side_url
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()
    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(cfg, "head")

    engine = create_engine(side_url, pool_size=5, max_overflow=5)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :name AND pid <> pg_backend_pid()"
                ),
                {"name": _SIDE_DB},
            )
            connection.execute(text(f"DROP DATABASE IF EXISTS {_SIDE_DB}"))
        admin.dispose()


def _queue(factory: sessionmaker[Session]) -> tuple[Session, ProcessingJob]:
    tenant_id = uuid4()
    session = factory()
    token = set_tenant_id(tenant_id)
    session.add(Tenant(id=tenant_id, name=f"pg-{tenant_id.hex[:8]}"))
    session.commit()
    job, reused = JobService(session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND,
        resource_type="document",
        resource_id=uuid4(),
    )
    assert reused is False
    session.info["tenant_token"] = token
    return session, job


def _close(session: Session) -> None:
    token = session.info.get("tenant_token")
    if token is not None:
        reset_tenant_id(token)
    session.close()


def test_two_postgres_sessions_cannot_claim_the_same_job(
    postgres_factory: sessionmaker[Session],
) -> None:
    setup, job = _queue(postgres_factory)
    job_id = job.id
    bind = setup.get_bind()
    assert bind is not None
    assert bind.dialect.name == "postgresql"
    _close(setup)

    barrier = Barrier(2)
    claimed: list[tuple[str, str | None]] = []
    errors: list[BaseException] = []

    def worker(name: str) -> None:
        session = postgres_factory()
        try:
            barrier.wait(timeout=5)
            row = JobService(session).claim(name)
            claimed.append((name, None if row is None else str(row.id)))
        except BaseException as exc:
            errors.append(exc)
        finally:
            session.close()

    threads = [Thread(target=worker, args=(name,)) for name in ("pg-worker-a", "pg-worker-b")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert errors == []
    assert [item for item in claimed if item[1] == str(job_id)]
    assert [item for item in claimed if item[1] is None]
    assert len(claimed) == 2

    check = postgres_factory()
    try:
        stored = check.get(ProcessingJob, job_id)
        assert stored is not None
        assert stored.status == JobStatus.RUNNING.value
        assert stored.attempt_count == 1
        assert stored.leased_by in {"pg-worker-a", "pg-worker-b"}
    finally:
        check.close()


def test_postgres_expired_lease_can_be_claimed_again(
    postgres_factory: sessionmaker[Session],
) -> None:
    session, job = _queue(postgres_factory)
    try:
        job.status = JobStatus.RUNNING.value
        job.attempt_count = 1
        job.leased_by = "crashed-worker"
        job.leased_until = datetime.now(UTC) - timedelta(minutes=10)
        session.commit()

        assert JobService(session).recover_expired_leases() == 1
        session.refresh(job)
        assert job.status == JobStatus.RETRY_SCHEDULED.value
        assert job.error_code == "lease_expired"
        assert job.leased_by is None

        job.run_after = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
        replacement = postgres_factory()
        try:
            claimed = JobService(replacement).claim("replacement-worker")
            assert claimed is not None
            assert claimed.id == job.id
            assert claimed.status == JobStatus.RUNNING.value
            assert claimed.attempt_count == 2
            assert claimed.leased_by == "replacement-worker"
        finally:
            replacement.close()
    finally:
        _close(session)


def test_postgres_transient_retry_stops_at_the_attempt_limit(
    postgres_factory: sessionmaker[Session],
) -> None:
    session, job = _queue(postgres_factory)
    try:
        claimed = JobService(session).claim("retry-worker")
        assert claimed is not None
        for attempt in (1, 2, 3):
            assert claimed.attempt_count == attempt
            JobService(session).mark_failed(
                claimed.id,
                code="worker_error",
                message="temporary",
                permanent=False,
            )
            session.refresh(claimed)
            if attempt < claimed.max_attempts:
                assert claimed.status == JobStatus.RETRY_SCHEDULED.value
                assert claimed.error_category == "transient"
                claimed.run_after = datetime.now(UTC) - timedelta(seconds=1)
                session.commit()
                claimed = JobService(session).claim("retry-worker")
                assert claimed is not None
                assert claimed.id == job.id
            else:
                assert claimed.status == JobStatus.FAILED.value
                assert claimed.error_category == "transient"
        assert JobService(session).claim("retry-worker") is None
    finally:
        _close(session)


def test_postgres_permanent_failure_is_not_reclaimed(
    postgres_factory: sessionmaker[Session],
) -> None:
    session, job = _queue(postgres_factory)
    try:
        claimed = JobService(session).claim("permanent-worker")
        assert claimed is not None
        JobService(session).mark_failed(
            job.id,
            code="PermanentJobError",
            message="This document cannot be processed.",
            permanent=True,
        )
        session.refresh(job)
        assert job.status == JobStatus.FAILED.value
        assert job.error_category == "permanent"
        assert job.attempt_count == 1
        assert JobService(session).claim("permanent-worker") is None
    finally:
        _close(session)
