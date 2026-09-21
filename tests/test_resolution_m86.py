"""M8.6 — Resolution audit trail and observability."""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    ExceptionReviewRoute,
    ReconciliationException,
    ResolutionAuditEvent,
    Vendor,
)
from app.db.session import get_db
from app.domain.enums import (
    ActionType,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ExecutionStatus,
    ResolutionAuditActorType,
    ResolutionAuditEventType,
)
from app.main import app
from app.resolution.audit import (
    ResolutionAuditError,
    ResolutionAuditWriter,
    sanitize_event_data,
)
from app.services.resolution_audit_service import ResolutionAuditService
from app.services.resolution_service import ResolutionService


@pytest.fixture
def api_client(db_session: Session) -> Generator[TestClient, None, None]:
    def _override() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.clear()


def _seed_exception(session: Session) -> ReconciliationException:
    exc = ReconciliationException(
        exception_type=ExceptionType.PRICE_MISMATCH.value,
        severity=ExceptionSeverity.HIGH.value,
        message="Invoice unit price exceeds PO",
        status=ExceptionStatus.OPEN.value,
        evidence={"po_price": "10.00", "invoice_price": "12.00"},
        fingerprint=f"fp-{uuid4()}",
    )
    session.add(exc)
    session.flush()
    return exc


def _full_lifecycle(session: Session) -> tuple[ResolutionService, object, object]:
    service = ResolutionService(session)
    plan = service.create_plan(
        reconciliation_exception_id=_seed_exception(session).id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
                "rationale": "needs review",
            }
        ],
        proposed_by="tester",
    )
    action = plan.proposed_actions[0]
    service.approve_action(
        plan.id,
        action.id,
        reviewer="alice@example.com",
        comment="ok",
    )
    service.execute_action(plan.id, action.id, idempotency_key="audit-exec-1")
    return service, plan, action


def test_lifecycle_audit_events(db_session: Session) -> None:
    _, plan, action = _full_lifecycle(db_session)
    events = ResolutionAuditService(db_session).get_plan_audit(plan.id)
    types = [e.event_type for e in events]
    assert ResolutionAuditEventType.PLAN_CREATED.value in types
    assert ResolutionAuditEventType.ACTION_PROPOSED.value in types
    assert ResolutionAuditEventType.ACTION_APPROVED.value in types
    assert ResolutionAuditEventType.EXECUTION_STARTED.value in types
    assert ResolutionAuditEventType.WORKFLOW_CREATED.value in types
    assert ResolutionAuditEventType.EXECUTION_SUCCEEDED.value in types

    proposed = next(
        e for e in events if e.event_type == ResolutionAuditEventType.ACTION_PROPOSED.value
    )
    assert proposed.actor_type == ResolutionAuditActorType.SYSTEM.value
    assert proposed.event_data["parameters_hash"]
    assert proposed.proposed_action_id == action.id

    approved = next(
        e for e in events if e.event_type == ResolutionAuditEventType.ACTION_APPROVED.value
    )
    assert approved.actor_type == ResolutionAuditActorType.HUMAN.value
    assert approved.actor_id == "alice@example.com"
    assert approved.event_data["approved_parameters_hash"]

    succeeded = next(
        e for e in events if e.event_type == ResolutionAuditEventType.EXECUTION_SUCCEEDED.value
    )
    assert succeeded.event_data["executed_parameters_hash"] == approved.event_data[
        "approved_parameters_hash"
    ]
    assert succeeded.event_data["reference_id"]


def test_rejection_audit_event(db_session: Session) -> None:
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=_seed_exception(db_session).id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.reject_action(plan.id, action.id, reviewer="bob@example.com", comment="no")
    events = ResolutionAuditService(db_session).get_plan_audit(plan.id)
    rejected = [
        e for e in events if e.event_type == ResolutionAuditEventType.ACTION_REJECTED.value
    ]
    assert len(rejected) == 1
    assert rejected[0].actor_id == "bob@example.com"


def test_execution_failed_and_retry_history(db_session: Session) -> None:
    service = ResolutionService(db_session)
    missing = uuid4()
    plan = service.create_plan(
        reconciliation_exception_id=_seed_exception(db_session).id,
        actions=[
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {"question": "Why?", "vendor_id": str(missing)},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    with pytest.raises(Exception, match="not found|failed"):
        service.execute_action(plan.id, action.id, idempotency_key="fail-a")

    events = ResolutionAuditService(db_session).get_plan_audit(plan.id)
    failed = [
        e for e in events if e.event_type == ResolutionAuditEventType.EXECUTION_FAILED.value
    ]
    assert len(failed) == 1
    assert failed[0].event_data["error_code"]
    assert "api_key" not in str(failed[0].event_data).lower()

    db_session.add(Vendor(id=missing, name="Acme", tax_id=f"T-{uuid4().hex[:6]}"))
    db_session.flush()
    service.execute_action(plan.id, action.id, idempotency_key="fail-b")
    events2 = ResolutionAuditService(db_session).get_plan_audit(plan.id)
    started = [
        e for e in events2 if e.event_type == ResolutionAuditEventType.EXECUTION_STARTED.value
    ]
    succeeded = [
        e
        for e in events2
        if e.event_type == ResolutionAuditEventType.EXECUTION_SUCCEEDED.value
    ]
    assert len(started) == 2
    assert len(succeeded) == 1
    assert len(
        [e for e in events2 if e.event_type == ResolutionAuditEventType.EXECUTION_FAILED.value]
    ) == 1


def test_idempotent_replay_does_not_duplicate_success_audit(db_session: Session) -> None:
    service, plan, action = _full_lifecycle(db_session)
    before = db_session.scalar(select(func.count()).select_from(ResolutionAuditEvent))
    replay = service.execute_action(plan.id, action.id, idempotency_key="audit-exec-1")
    assert replay.execution_status == ExecutionStatus.SUCCEEDED.value
    after = db_session.scalar(select(func.count()).select_from(ResolutionAuditEvent))
    assert after == before
    assert db_session.scalar(select(func.count()).select_from(ExceptionReviewRoute)) == 1


def test_workflow_reused_event(db_session: Session) -> None:
    # Force handler already_exists path via a second execution attempt that
    # somehow runs the handler again is blocked by idempotency; instead verify
    # WORKFLOW_CREATED on first success and that replay does not add WORKFLOW_REUSED.
    _, plan, _ = _full_lifecycle(db_session)
    events = ResolutionAuditService(db_session).get_plan_audit(plan.id)
    created = [
        e for e in events if e.event_type == ResolutionAuditEventType.WORKFLOW_CREATED.value
    ]
    reused = [
        e for e in events if e.event_type == ResolutionAuditEventType.WORKFLOW_REUSED.value
    ]
    assert len(created) == 1
    assert len(reused) == 0
    assert created[0].event_data["workflow_type"] == ActionType.ROUTE_TO_REVIEW.value


def test_chronological_ordering_and_tiebreak(db_session: Session) -> None:
    _, plan, _ = _full_lifecycle(db_session)
    events = ResolutionAuditService(db_session).get_plan_audit(plan.id)
    pairs = [(e.created_at, str(e.id)) for e in events]
    assert pairs == sorted(pairs)


def test_audit_immutability_update_delete(db_session: Session) -> None:
    _, plan, _ = _full_lifecycle(db_session)
    row = db_session.scalars(
        select(ResolutionAuditEvent).where(ResolutionAuditEvent.resolution_plan_id == plan.id)
    ).first()
    assert row is not None
    row.event_type = "FABRICATED"
    with pytest.raises(ResolutionAuditError, match="append-only"):
        db_session.flush()
    db_session.rollback()

    row = db_session.scalars(
        select(ResolutionAuditEvent).where(ResolutionAuditEvent.resolution_plan_id == plan.id)
    ).first()
    assert row is not None
    db_session.delete(row)
    with pytest.raises(ResolutionAuditError, match="append-only|deletes"):
        db_session.flush()
    db_session.rollback()


def test_arbitrary_event_type_rejected(db_session: Session) -> None:
    writer = ResolutionAuditWriter(db_session)
    with pytest.raises(ResolutionAuditError, match="Unknown audit event type"):
        writer.record(
            event_type="EXECUTION_SUCCEEDED",  # type: ignore[arg-type]
            actor_type=ResolutionAuditActorType.SYSTEM,
        )


def test_sanitize_strips_secrets() -> None:
    cleaned = sanitize_event_data(
        {"ok": 1, "api_key": "secret", "nested": {"password": "x", "ref": "y"}}
    )
    assert cleaned == {"ok": 1, "nested": {"ref": "y"}}


def test_plan_audit_isolation(api_client: TestClient, db_session: Session) -> None:
    service = ResolutionService(db_session)
    plan_a = service.create_plan(
        reconciliation_exception_id=_seed_exception(db_session).id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "a"},
            }
        ],
    )
    plan_b = service.create_plan(
        reconciliation_exception_id=_seed_exception(db_session).id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "b"},
            }
        ],
    )
    db_session.commit()
    resp = api_client.get(f"/resolution-plans/{plan_a.id}/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert body["plan_id"] == str(plan_a.id)
    assert body["count"] >= 2
    assert all(
        (e.get("data") or {}).get("exception_id") != str(plan_b.reconciliation_exception_id)
        or e["event_type"] == ResolutionAuditEventType.PLAN_CREATED.value
        for e in body["events"]
    )
    # Ensure no event from plan_b leaks by id correlation on action proposals
    action_b = plan_b.proposed_actions[0].id
    assert all(e.get("proposed_action_id") != str(action_b) for e in body["events"])

    missing = api_client.get(f"/resolution-plans/{uuid4()}/audit")
    assert missing.status_code == 404


def test_api_audit_endpoint_shape(api_client: TestClient, db_session: Session) -> None:
    _, plan, _ = _full_lifecycle(db_session)
    db_session.commit()
    resp = api_client.get(f"/resolution-plans/{plan.id}/audit")
    assert resp.status_code == 200
    event = resp.json()["events"][0]
    assert {"id", "event_type", "actor_type", "created_at", "data"} <= set(event.keys())
    assert "api_key" not in str(resp.json()).lower()
