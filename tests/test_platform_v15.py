"""Auth, tenant isolation, and durable document jobs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_principal
from app.core.config import get_settings
from app.db.base import Base
from app.db.models import Document, ProcessingJob, Tenant
from app.db.session import get_db
from app.db.tenant_filter import current_tenant_id, reset_tenant_id, set_tenant_id
from app.domain.enums import JobStatus, JobType, MembershipRole
from app.identity.service import AuthError, AuthService
from app.main import app
from app.services.document_service import DocumentService
from app.services.job_service import JobService
from app.services.policy_service import PolicyService
from app.storage.local import LocalFileStorage
from app.workers.runner import PermanentJobError, run_available
from tests.conftest import TEST_TENANT_ID

PDF = b"%PDF-1.4 platform"
client = TestClient(app)


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


def test_users_cannot_read_another_tenants_document(
    db_session: Session, sqlite_engine, storage_root: Path
) -> None:
    other = uuid4()
    db_session.add(Tenant(id=other, name="Other"))
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(filename="a.pdf", content_type="application/pdf", data=PDF)
    assert row.tenant_id == TEST_TENANT_ID
    db_session.commit()
    other_session = sessionmaker(bind=sqlite_engine, expire_on_commit=False)()
    token = set_tenant_id(other)
    try:
        assert other_session.get(Document, row.id) is None
        assert list(other_session.scalars(select(Document))) == []
    finally:
        reset_tenant_id(token)
        other_session.close()


def test_legacy_null_tenant_rows_stay_hidden(
    db_session: Session, sqlite_engine, storage_root: Path
) -> None:
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(filename="b.pdf", content_type="application/pdf", data=PDF + b"-b")
    row.tenant_id = None
    db_session.commit()
    fresh = sessionmaker(bind=sqlite_engine, expire_on_commit=False)()
    try:
        assert current_tenant_id() == TEST_TENANT_ID
        assert fresh.get(Document, row.id) is None
    finally:
        fresh.close()


def test_duplicate_understand_reuses_queued_job(db_session: Session, storage_root: Path) -> None:
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(filename="c.pdf", content_type="application/pdf", data=PDF + b"-c")
    from app.domain.enums import JobType

    first, reused = JobService(db_session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND, resource_type="document", resource_id=row.id
    )
    second, reused_again = JobService(db_session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND, resource_type="document", resource_id=row.id
    )
    assert reused is False
    assert reused_again is True
    assert first.id == second.id
    assert db_session.get(ProcessingJob, first.id) is not None


def test_worker_completes_understanding_once(db_session: Session, storage_root: Path) -> None:
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(filename="d.pdf", content_type="application/pdf", data=PDF + b"-d")
    from app.domain.enums import JobType

    JobService(db_session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND, resource_type="document", resource_id=row.id
    )
    assert run_available(db_session, worker_id="test") == 1
    assert run_available(db_session, worker_id="test") == 0
    job = db_session.query(ProcessingJob).one()
    assert job.status == JobStatus.SUCCEEDED.value


def test_expired_lease_is_recovered(db_session: Session, storage_root: Path) -> None:
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(filename="e.pdf", content_type="application/pdf", data=PDF + b"-e")
    from app.domain.enums import JobType

    job, _ = JobService(db_session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND, resource_type="document", resource_id=row.id
    )
    job.status = JobStatus.RUNNING.value
    job.attempt_count = 1
    job.leased_until = datetime.now(UTC) - timedelta(minutes=10)
    db_session.commit()
    assert JobService(db_session).recover_expired_leases() == 1
    db_session.refresh(job)
    assert job.status == JobStatus.RETRY_SCHEDULED.value


def test_login_csrf_and_viewer_cannot_upload(db_session: Session) -> None:
    app.dependency_overrides.pop(get_principal, None)

    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    try:
        AuthService(db_session).bootstrap(
            email="admin@example.com",
            password="correct-horse-battery",
            tenant_name="Northstar",
        )
        AuthService(db_session).provision_user(
            email="viewer@example.com",
            password="another-strong-pass",
            role=MembershipRole.VIEWER,
            tenant_id=db_session.scalar(select(Tenant).where(Tenant.name == "Northstar")).id,
        )
        anonymous = client.get("/documents")
        assert anonymous.status_code == 401
        logged_in = client.post(
            "/auth/login",
            json={"email": "viewer@example.com", "password": "another-strong-pass"},
        )
        assert logged_in.status_code == 200
        assert logged_in.json()["role"] == "viewer"
        csrf = logged_in.cookies.get("reconai_csrf")
        denied = client.post(
            "/documents",
            files={"file": ("a.pdf", PDF, "application/pdf")},
            headers={"X-CSRF-Token": csrf or ""},
        )
        assert denied.status_code == 403, denied.text
        listed = client.get("/documents")
        assert listed.status_code == 200
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.cookies.clear()


def test_http_session_cannot_read_another_tenants_document(
    db_session: Session, sqlite_engine, storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    factory = sessionmaker(bind=sqlite_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr("app.api.middleware.get_session_factory", lambda: factory)
    other = uuid4()
    db_session.add(Tenant(id=other, name="Other"))
    db_session.commit()
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(
        filename="secret.pdf", content_type="application/pdf", data=PDF + b"-secret"
    )
    policy = PolicyService(db_session).create_document(name="Secret policy")
    job, _ = JobService(db_session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND,
        resource_type="document",
        resource_id=row.id,
    )
    db_session.commit()
    app.dependency_overrides.pop(get_principal, None)

    def _db():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _db
    try:
        AuthService(db_session).provision_user(
            email="other@example.com",
            password="another-strong-pass",
            role=MembershipRole.VIEWER,
            tenant_id=other,
        )
        logged_in = client.post(
            "/auth/login",
            json={"email": "other@example.com", "password": "another-strong-pass"},
        )
        assert logged_in.status_code == 200
        listed = client.get("/documents")
        assert listed.status_code == 200
        assert all(item["id"] != str(row.id) for item in listed.json()["items"])
        hidden = client.get(f"/documents/{row.id}")
        assert hidden.status_code == 404
        assert client.get(f"/policies/{policy.id}").status_code == 404
        assert client.get(f"/jobs/{job.id}").status_code == 404
        assert client.get("/jobs").json()["counts"] == {}
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.cookies.clear()


def test_bootstrap_rejects_a_second_admin_and_a_weak_password(db_session: Session) -> None:
    service = AuthService(db_session)
    service.bootstrap(
        email="owner@example.com",
        password="correct-horse-battery",
        tenant_name="Northstar",
    )
    with pytest.raises(AuthError):
        service.bootstrap(
            email="other@example.com",
            password="correct-horse-battery",
            tenant_name="Elsewhere",
        )
    with pytest.raises(AuthError):
        service.provision_user(
            email="weak@example.com",
            password="password",
            role=MembershipRole.VIEWER,
            tenant_id=TEST_TENANT_ID,
        )


def test_cached_get_does_not_cross_tenants(db_session: Session, storage_root: Path) -> None:
    other = uuid4()
    db_session.add(Tenant(id=other, name="Other"))
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(
        filename="cached.pdf", content_type="application/pdf", data=PDF + b"-cached"
    )
    db_session.commit()
    assert db_session.get(Document, row.id) is row
    token = set_tenant_id(other)
    try:
        assert db_session.get(Document, row.id) is None
    finally:
        reset_tenant_id(token)
    assert db_session.get(Document, row.id) is row


def test_role_boundaries_for_consequential_actions(db_session: Session) -> None:
    app.dependency_overrides.pop(get_principal, None)

    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    missing = "00000000-0000-4000-8000-000000000099"
    password = "another-strong-pass"
    try:
        _, admin = AuthService(db_session).bootstrap(
            email="admin@example.com",
            password="correct-horse-battery",
            tenant_name="Northstar",
        )
        tenant_id = db_session.scalar(select(Tenant).where(Tenant.name == "Northstar")).id
        del admin
        for email, role in (
            ("viewer@example.com", MembershipRole.VIEWER),
            ("operator@example.com", MembershipRole.OPERATOR),
            ("reviewer@example.com", MembershipRole.REVIEWER),
            ("approver@example.com", MembershipRole.APPROVER),
        ):
            AuthService(db_session).provision_user(
                email=email, password=password, role=role, tenant_id=tenant_id
            )

        def headers_for(email: str, secret: str) -> dict[str, str]:
            client.cookies.clear()
            logged = client.post("/auth/login", json={"email": email, "password": secret})
            assert logged.status_code == 200, logged.text
            return {"X-CSRF-Token": logged.cookies.get("reconai_csrf") or ""}

        def status_of(email: str, secret: str, method: str, path: str, **kwargs: object) -> int:
            return client.request(
                method, path, headers=headers_for(email, secret), **kwargs
            ).status_code  # type: ignore[arg-type]

        promote = f"/review/tasks/{missing}/promote"
        review_approve = f"/review/tasks/{missing}/approve"
        plan = f"/reconciliation/exceptions/{missing}/resolution-plan"
        approve = f"/resolution-plans/{missing}/actions/{missing}/approve"
        execute = f"/resolution-plans/{missing}/actions/{missing}/execute"
        decision = {"reviewer": "owner@example.com", "comment": "checked"}
        review_decision = {"reviewer": "owner@example.com", "reason": "checked"}

        viewer = headers_for("viewer@example.com", password)
        assert (
            client.post(
                "/documents", files={"file": ("a.pdf", PDF, "application/pdf")}, headers=viewer
            ).status_code
            == 403
        )
        assert client.post(promote, headers=viewer).status_code == 403
        assert client.post(review_approve, json=review_decision, headers=viewer).status_code == 403
        assert client.post(plan, headers=viewer).status_code == 403
        assert client.post(approve, json=decision, headers=viewer).status_code == 403
        assert (
            client.post(execute, json={"idempotency_key": "once"}, headers=viewer).status_code
            == 403
        )
        assert (
            client.post("/policies", json={"name": "Viewer policy"}, headers=viewer).status_code
            == 403
        )
        assert client.post("/auth/logout", headers=viewer).status_code == 200
        assert client.get("/documents").status_code == 401

        operator = "operator@example.com"
        assert status_of(operator, password, "POST", promote) == 403
        assert status_of(operator, password, "POST", approve, json=decision) == 403
        assert (
            status_of(operator, password, "POST", execute, json={"idempotency_key": "once"}) == 403
        )
        assert (
            status_of(operator, password, "POST", "/policies", json={"name": "Operator policy"})
            == 403
        )
        uploaded = client.post(
            "/documents",
            files={"file": ("a.pdf", PDF, "application/pdf")},
            headers=headers_for(operator, password),
        )
        assert uploaded.status_code != 403

        reviewer = "reviewer@example.com"
        assert status_of(reviewer, password, "POST", promote) == 404
        assert status_of(reviewer, password, "POST", review_approve, json=review_decision) == 404
        assert status_of(reviewer, password, "POST", approve, json=decision) == 403
        assert (
            status_of(reviewer, password, "POST", execute, json={"idempotency_key": "once"}) == 403
        )
        assert (
            status_of(reviewer, password, "POST", "/policies", json={"name": "Reviewer policy"})
            == 403
        )
        assert status_of(reviewer, password, "POST", plan) == 403

        approver = "approver@example.com"
        assert status_of(approver, password, "POST", approve, json=decision) == 404
        assert status_of(approver, password, "POST", plan) == 404
        assert (
            status_of(approver, password, "POST", execute, json={"idempotency_key": "once"}) == 403
        )
        assert status_of(approver, password, "POST", promote) == 403
        assert status_of(approver, password, "POST", review_approve, json=review_decision) == 403
        assert (
            status_of(approver, password, "POST", "/policies", json={"name": "Approver policy"})
            == 403
        )

        admin = headers_for("admin@example.com", "correct-horse-battery")
        created = client.post("/policies", json={"name": "Admin policy"}, headers=admin)
        assert created.status_code == 201
        bare_logout = client.post("/auth/logout")
        assert bare_logout.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
        client.cookies.clear()


def _queue(db_session: Session, storage_root: Path, name: str) -> ProcessingJob:
    service = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    row, _ = service.upload(filename=name, content_type="application/pdf", data=PDF + name.encode())
    job, reused = JobService(db_session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND,
        resource_type="document",
        resource_id=row.id,
    )
    assert reused is False
    return job


def test_two_workers_cannot_claim_the_same_job(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite:///{(tmp_path / 'claims.db').as_posix()}",
        connect_args={"check_same_thread": False, "timeout": 5},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    token = set_tenant_id(TEST_TENANT_ID)
    try:
        setup = factory()
        setup.add(Tenant(id=TEST_TENANT_ID, name="Claim tenant"))
        setup.commit()
        job, reused = JobService(setup).enqueue(
            job_type=JobType.DOCUMENT_UNDERSTAND,
            resource_type="document",
            resource_id=uuid4(),
        )
        assert reused is False
        job_id = job.id
        setup.close()

        barrier = Barrier(2)
        claimed: list[str | None] = []
        errors: list[BaseException] = []

        def worker(name: str) -> None:
            session = factory()
            try:
                barrier.wait(timeout=5)
                row = JobService(session).claim(name)
                claimed.append(None if row is None else str(row.id))
            except BaseException as exc:
                errors.append(exc)
            finally:
                session.close()

        threads = [Thread(target=worker, args=(name,)) for name in ("worker-a", "worker-b")]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)

        assert errors == []
        assert claimed.count(str(job_id)) == 1
        assert claimed.count(None) == 1
        check = factory()
        try:
            stored = check.get(ProcessingJob, job_id)
            assert stored is not None
            assert stored.status == JobStatus.RUNNING.value
            assert stored.attempt_count == 1
            assert stored.leased_by in {"worker-a", "worker-b"}
        finally:
            check.close()
    finally:
        reset_tenant_id(token)
        engine.dispose()


def test_transient_errors_retry_until_the_attempt_limit(
    db_session: Session, storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _queue(db_session, storage_root, "retry.pdf")

    def fail(session: Session, current: ProcessingJob) -> None:
        del session, current
        raise RuntimeError("temporary")

    monkeypatch.setattr("app.workers.runner._dispatch", fail)
    for attempt in (1, 2, 3):
        assert run_available(db_session, worker_id="retry-worker") == 1
        db_session.refresh(job)
        assert job.attempt_count == attempt
        assert job.error_code == "worker_error"
        if attempt < job.max_attempts:
            assert job.status == JobStatus.RETRY_SCHEDULED.value
            assert job.error_category == "transient"
            job.run_after = datetime.now(UTC) - timedelta(seconds=1)
            db_session.commit()
        else:
            assert job.status == JobStatus.FAILED.value
            assert job.error_category == "transient"
    assert run_available(db_session, worker_id="retry-worker") == 0


def test_missing_document_is_not_retried(db_session: Session, storage_root: Path) -> None:
    del storage_root
    job, reused = JobService(db_session).enqueue(
        job_type=JobType.DOCUMENT_UNDERSTAND,
        resource_type="document",
        resource_id=uuid4(),
    )
    assert reused is False
    assert run_available(db_session, worker_id="missing-worker") == 1
    db_session.refresh(job)
    assert job.status == JobStatus.FAILED.value
    assert job.error_category == "permanent"
    assert job.error_code == "DocumentUnderstandingNotFoundError"
    assert job.attempt_count == 1
    assert run_available(db_session, worker_id="missing-worker") == 0


def test_permanent_errors_do_not_retry_and_stay_visible(
    db_session: Session, storage_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job = _queue(db_session, storage_root, "permanent.pdf")

    def fail(session: Session, current: ProcessingJob) -> None:
        del session, current
        raise PermanentJobError("This document cannot be processed.")

    monkeypatch.setattr("app.workers.runner._dispatch", fail)
    assert run_available(db_session, worker_id="permanent-worker") == 1
    db_session.refresh(job)
    assert job.status == JobStatus.FAILED.value
    assert job.error_category == "permanent"
    assert job.attempt_count == 1
    assert job.error_message == "This document cannot be processed."
    assert run_available(db_session, worker_id="permanent-worker") == 0

    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    try:
        listed = client.get("/jobs")
        assert listed.status_code == 200
        assert listed.json()["counts"][JobStatus.FAILED.value] >= 1
        detail = client.get(f"/jobs/{job.id}")
        assert detail.status_code == 200
        body = detail.json()
        assert body["status"] == JobStatus.FAILED.value
        assert body["error_category"] == "permanent"
        assert "\\" not in body["error_message"]
        assert "password" not in body["error_message"].lower()
    finally:
        app.dependency_overrides.pop(get_db, None)
