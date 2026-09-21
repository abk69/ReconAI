"""M8.5 — Controlled action execution."""

from __future__ import annotations

from collections.abc import Generator
from threading import Barrier, Thread
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db import models as _models  # noqa: F401 — register mappers
from app.db.base import Base
from app.db.models import (
    ActionExecution,
    ExceptionReviewRoute,
    ManagerEscalation,
    MissingDocumentRequest,
    ReconciliationException,
    Vendor,
    VendorClarificationRequest,
)
from app.db.session import get_db
from app.domain.enums import (
    ActionType,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.main import app
from app.resolution.guardrails import aggregate_plan_status, validate_action_order
from app.resolution.registry import ActionRegistry, build_default_registry
from app.services.resolution_execution_service import ResolutionExecutionService
from app.services.resolution_service import (
    ResolutionService,
    ResolutionValidationError,
)


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


def _seed_vendor(session: Session) -> Vendor:
    vendor = Vendor(name="Acme Supplies", tax_id=f"TAX-{uuid4().hex[:8]}")
    session.add(vendor)
    session.flush()
    return vendor


def _approved_plan(session: Session, actions: list[dict]):
    exc = _seed_exception(session)
    service = ResolutionService(session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        reasoning_summary="M8.5 execution",
        actions=actions,
    )
    for action in plan.proposed_actions:
        service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    session.refresh(plan)
    return service, plan


# ── Success paths ──────────────────────────────────────────────────────────


def test_route_to_review_executes(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = service.execute_action(plan.id, action.id, idempotency_key="route-ok")
    assert execution.execution_status == ExecutionStatus.SUCCEEDED.value
    assert execution.result is not None
    assert execution.result["reference_id"] is not None
    assert db_session.scalar(select(func.count()).select_from(ExceptionReviewRoute)) == 1
    db_session.refresh(action)
    db_session.refresh(plan)
    assert action.status == ProposedActionStatus.COMPLETED.value
    assert plan.status == ResolutionPlanStatus.COMPLETED.value


def test_vendor_clarification_executes(db_session: Session) -> None:
    vendor = _seed_vendor(db_session)
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {
                    "question": "Please confirm unit price",
                    "vendor_id": str(vendor.id),
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = service.execute_action(plan.id, action.id, idempotency_key="vend-ok")
    assert execution.result["reference_id"] is not None
    assert db_session.scalar(select(func.count()).select_from(VendorClarificationRequest)) == 1


def test_missing_document_executes(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {
                    "document_type": "PACKING_SLIP",
                    "reason": "Packing slip not attached",
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = service.execute_action(plan.id, action.id, idempotency_key="miss-ok")
    assert execution.result["reference_id"] is not None
    assert db_session.scalar(select(func.count()).select_from(MissingDocumentRequest)) == 1


def test_escalate_executes(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {"reason": "High variance", "destination": "AP_MANAGER"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = service.execute_action(plan.id, action.id, idempotency_key="esc-ok")
    assert execution.result["reference_id"] is not None
    assert db_session.scalar(select(func.count()).select_from(ManagerEscalation)) == 1


# ── Guardrails / safety ────────────────────────────────────────────────────


def test_execution_without_approval_rejected(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    with pytest.raises(ResolutionValidationError, match="PENDING|Approval-required"):
        service.execute_action(plan.id, action.id, idempotency_key="no-appr")


def test_rejected_action_cannot_execute(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.reject_action(plan.id, action.id, reviewer="bob@example.com")
    with pytest.raises(ResolutionValidationError, match="REJECTED|reject"):
        service.execute_action(plan.id, action.id, idempotency_key="rej")


def test_cancelled_plan_cannot_execute(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    plan.status = ResolutionPlanStatus.CANCELLED.value
    db_session.flush()
    with pytest.raises(ResolutionValidationError, match="CANCELLED"):
        service.execute_action(plan.id, action.id, idempotency_key="cancel")


def test_client_cannot_override_parameters(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    original = dict(action.parameters)
    # Execute API / service only accept idempotency_key — stored params win.
    service.execute_action(plan.id, action.id, idempotency_key="params-lock")
    db_session.refresh(action)
    assert dict(action.parameters) == original


def test_llm_never_called_during_execution(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("LLM must not be called during execution")

    monkeypatch.setattr("app.llm.gemini.GeminiProvider.generate_structured", _boom)
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.execute_action(plan.id, action.id, idempotency_key="no-llm")


def test_handler_only_via_registry(db_session: Session) -> None:
    registry = ActionRegistry()
    # Empty registry — registered types cannot resolve.
    service = ResolutionService(db_session, registry=registry)
    exc = _seed_exception(db_session)
    with pytest.raises(Exception, match="Unknown|not registered|Unregistered"):
        service.create_plan(
            reconciliation_exception_id=exc.id,
            actions=[
                {
                    "action_type": ActionType.ROUTE_TO_REVIEW,
                    "parameters": {"review_queue": "x"},
                }
            ],
        )


def test_unknown_action_type_blocked(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    action.action_type = "DELETE_INVOICE"
    with pytest.raises(Exception, match="action_type|Cannot mutate"):
        db_session.flush()
    db_session.rollback()


# ── Ordering / plan aggregation ────────────────────────────────────────────


def test_action_order_blocks_later_action(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {
                    "document_type": "PACKING_SLIP",
                    "reason": "Need packing slip",
                },
            },
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            },
        ],
    )
    actions = sorted(plan.proposed_actions, key=lambda a: a.action_order)
    with pytest.raises(ResolutionValidationError, match="action_order"):
        service.execute_action(plan.id, actions[1].id, idempotency_key="order-skip")

    service.execute_action(plan.id, actions[0].id, idempotency_key="order-1")
    db_session.refresh(plan)
    assert plan.status == ResolutionPlanStatus.APPROVED.value

    service.execute_action(plan.id, actions[1].id, idempotency_key="order-2")
    db_session.refresh(plan)
    assert plan.status == ResolutionPlanStatus.COMPLETED.value


def test_aggregate_plan_status_helpers() -> None:
    class _A:
        def __init__(self, status: str) -> None:
            self.status = status

    assert (
        aggregate_plan_status([_A(ProposedActionStatus.EXECUTING.value)])
        is ResolutionPlanStatus.EXECUTING
    )
    assert (
        aggregate_plan_status([_A(ProposedActionStatus.PENDING.value)])
        is ResolutionPlanStatus.APPROVAL_REQUIRED
    )
    assert (
        aggregate_plan_status([_A(ProposedActionStatus.FAILED.value)])
        is ResolutionPlanStatus.FAILED
    )
    assert (
        aggregate_plan_status([_A(ProposedActionStatus.COMPLETED.value)])
        is ResolutionPlanStatus.COMPLETED
    )


# ── Failure / retry / idempotency ──────────────────────────────────────────


def test_handler_failure_savepoint_and_retry(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    missing_vendor_id = uuid4()
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {
                    "question": "Why?",
                    "vendor_id": str(missing_vendor_id),
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    with pytest.raises(ResolutionValidationError, match="not found|failed"):
        service.execute_action(plan.id, action.id, idempotency_key="fail-1")

    db_session.refresh(action)
    db_session.refresh(plan)
    assert action.status == ProposedActionStatus.FAILED.value
    assert plan.status == ResolutionPlanStatus.FAILED.value
    assert db_session.scalar(select(func.count()).select_from(VendorClarificationRequest)) == 0
    failed_row = db_session.scalar(
        select(ActionExecution).where(ActionExecution.idempotency_key == "fail-1")
    )
    assert failed_row is not None
    assert failed_row.execution_status == ExecutionStatus.FAILED.value
    assert failed_row.error_code is not None

    # Same approved parameters; create the vendor that the hash-bound payload references.
    db_session.add(
        Vendor(
            id=missing_vendor_id,
            name="Acme Supplies",
            tax_id=f"TAX-{uuid4().hex[:8]}",
        )
    )
    db_session.flush()
    retry = service.execute_action(plan.id, action.id, idempotency_key="fail-2")
    assert retry.execution_status == ExecutionStatus.SUCCEEDED.value
    assert db_session.scalar(select(func.count()).select_from(VendorClarificationRequest)) == 1


def test_idempotency_same_key_and_different_key(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    first = service.execute_action(plan.id, action.id, idempotency_key="idem-a")
    second = service.execute_action(plan.id, action.id, idempotency_key="idem-a")
    assert first.id == second.id
    assert db_session.scalar(select(func.count()).select_from(ExceptionReviewRoute)) == 1
    with pytest.raises(ResolutionValidationError, match="already has an active"):
        service.execute_action(plan.id, action.id, idempotency_key="idem-b")


def test_concurrent_duplicate_execution_one_side_effect(tmp_path) -> None:
    """Two threads racing the same key produce one workflow side effect."""
    db_path = tmp_path / "m85_concurrency.db"
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )

    def _fk(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine, "connect", _fk)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    setup = factory()
    exc = _seed_exception(setup)
    service = ResolutionService(setup)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action_id = plan.proposed_actions[0].id
    plan_id = plan.id
    service.approve_action(plan_id, action_id, reviewer="alice@example.com")
    setup.commit()
    setup.close()

    barrier = Barrier(2)
    results: list[object] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        session = factory()
        try:
            barrier.wait(timeout=5)
            exec_svc = ResolutionExecutionService(session)
            row = exec_svc.execute_action(plan_id, action_id, idempotency_key="race-key")
            results.append(row.id)
            session.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
            session.rollback()
        finally:
            session.close()

    threads = [Thread(target=_worker), Thread(target=_worker)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    verify = factory()
    count = verify.scalar(select(func.count()).select_from(ExceptionReviewRoute))
    exec_count = verify.scalar(select(func.count()).select_from(ActionExecution))
    verify.close()
    engine.dispose()

    assert count == 1
    assert exec_count == 1
    # Both succeeded via idempotent reuse, or one conflicted safely.
    assert len(results) + len(errors) == 2
    if results:
        assert len(set(str(r) for r in results)) == 1


def test_m2_financial_truth_unchanged(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    exc = db_session.get(ReconciliationException, plan.reconciliation_exception_id)
    assert exc is not None
    before = exc.status
    service.execute_action(plan.id, action.id, idempotency_key="m2-safe")
    db_session.refresh(exc)
    assert exc.status == before


# ── API ────────────────────────────────────────────────────────────────────


def test_execute_api_success(api_client: TestClient, db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action_id = plan.proposed_actions[0].id
    db_session.commit()

    resp = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/execute",
        json={"idempotency_key": "api-exec-m85"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["plan_id"] == str(plan.id)
    assert body["action_id"] == str(action_id)
    assert body["action_type"] == ActionType.ROUTE_TO_REVIEW.value
    assert body["execution_id"]
    assert body["execution_status"] == ExecutionStatus.SUCCEEDED.value
    assert body["action_status"] == ProposedActionStatus.COMPLETED.value
    assert body["plan_status"] == ResolutionPlanStatus.COMPLETED.value
    assert body["idempotency_key"] == "api-exec-m85"
    assert body["result"]["reference_id"] is not None
    assert body["reused_existing"] is False

    replay = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/execute",
        json={"idempotency_key": "api-exec-m85"},
    )
    assert replay.status_code == 200
    assert replay.json()["execution_id"] == body["execution_id"]
    assert replay.json()["reused_existing"] is True


def test_execute_api_missing_approval(api_client: TestClient, db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action_id = plan.proposed_actions[0].id
    db_session.commit()
    resp = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/execute",
        json={"idempotency_key": "api-no-appr"},
    )
    assert resp.status_code == 409


def test_execute_api_wrong_ownership(api_client: TestClient, db_session: Session) -> None:
    _, plan_a = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "a"},
            }
        ],
    )
    _, plan_b = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "b"},
            }
        ],
    )
    action_b = plan_b.proposed_actions[0].id
    db_session.commit()
    resp = api_client.post(
        f"/resolution-plans/{plan_a.id}/actions/{action_b}/execute",
        json={"idempotency_key": "api-wrong"},
    )
    assert resp.status_code == 404


def test_default_registry_has_four_handlers() -> None:
    assert len(build_default_registry().list_available()) == 4


def test_validate_action_order_unit(db_session: Session) -> None:
    service, plan = _approved_plan(
        db_session,
        [
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "a"},
            },
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "b"},
            },
        ],
    )
    actions = sorted(plan.proposed_actions, key=lambda a: a.action_order)
    from app.resolution.guardrails import GuardrailError

    with pytest.raises(GuardrailError, match="action_order"):
        validate_action_order(actions[1], actions)
