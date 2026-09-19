"""M8.2 — Safe action handlers, workflow records, and execution API."""

from __future__ import annotations

from collections.abc import Generator
from datetime import date
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentExtractionResult,
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
    DocumentStatus,
    DocumentType,
    EscalationPriority,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ExecutionStatus,
    ExtractionOutcome,
    ProposedActionStatus,
    ResolutionPlanStatus,
    WorkflowRequestStatus,
)
from app.main import app
from app.resolution.contracts import (
    EscalateToManagerParameters,
    RequestMissingDocumentParameters,
    RequestVendorClarificationParameters,
    RouteToReviewParameters,
    parse_action_parameters,
)
from app.resolution.registry import ActionRegistry, build_default_registry
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


def _approve_and_execute(
    service: ResolutionService,
    plan_id,
    action_id,
    *,
    key: str,
) -> object:
    service.approve_action(plan_id, action_id, reviewer="alice")
    return service.execute_action(plan_id, action_id, idempotency_key=key)


# --- Registry ---


def test_all_four_actions_registered() -> None:
    registry = build_default_registry()
    assert set(registry.list_available()) == {
        ActionType.ROUTE_TO_REVIEW,
        ActionType.REQUEST_VENDOR_CLARIFICATION,
        ActionType.REQUEST_MISSING_DOCUMENT,
        ActionType.ESCALATE_TO_MANAGER,
    }


def test_registry_metadata() -> None:
    meta = build_default_registry().list_metadata()
    assert len(meta) == 4
    for item in meta:
        assert "action_type" in item
        assert "description" in item
        assert "requires_approval" in item
        assert item["requires_approval"] is True
        assert "parameter_schema" in item
        assert "parameters_json_schema" in item


def test_unknown_action_rejected_by_registry() -> None:
    registry = build_default_registry()
    with pytest.raises(KeyError):
        registry.get("MODIFY_INVOICE")
    empty = ActionRegistry()
    assert empty.list_available() == []


# --- Parameter validation ---


def test_valid_parameters() -> None:
    assert parse_action_parameters(
        ActionType.ROUTE_TO_REVIEW, {"review_queue": "procurement", "reason": "check"}
    )
    assert parse_action_parameters(
        ActionType.REQUEST_VENDOR_CLARIFICATION,
        {"question": "Why the variance?", "vendor_reference": "V-1"},
    )
    assert parse_action_parameters(
        ActionType.REQUEST_MISSING_DOCUMENT,
        {"document_type": "GRN", "reason": "Not attached"},
    )
    assert parse_action_parameters(
        ActionType.ESCALATE_TO_MANAGER,
        {"reason": "Needs manager", "priority": "HIGH"},
    )


def test_missing_required_fields() -> None:
    with pytest.raises(ValidationError):
        RouteToReviewParameters.model_validate({})
    with pytest.raises(ValidationError):
        RequestVendorClarificationParameters.model_validate({"question": "hi"})
    with pytest.raises(ValidationError):
        RequestMissingDocumentParameters.model_validate({"document_type": "PO"})
    with pytest.raises(ValidationError):
        EscalateToManagerParameters.model_validate({})


def test_invalid_enum_and_empty_strings() -> None:
    with pytest.raises(ValidationError):
        EscalateToManagerParameters.model_validate(
            {"reason": "x", "priority": "CRITICAL"}
        )
    with pytest.raises(ValidationError):
        RouteToReviewParameters.model_validate({"review_queue": "   "})
    with pytest.raises(ValidationError):
        RequestMissingDocumentParameters.model_validate(
            {"document_type": "PO", "reason": ""}
        )


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteToReviewParameters.model_validate(
            {"review_queue": "procurement", "sql": "DROP TABLE invoices"}
        )
    with pytest.raises(ValidationError):
        parse_action_parameters(
            ActionType.ESCALATE_TO_MANAGER,
            {"reason": "x", "shell": "rm -rf /"},
        )


def test_malformed_ids_rejected() -> None:
    with pytest.raises(ValidationError):
        RequestVendorClarificationParameters.model_validate(
            {"question": "q", "vendor_id": "not-a-uuid"}
        )


# --- Approval ---


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
    with pytest.raises(ResolutionValidationError, match="Approval-required"):
        service.execute_action(plan.id, action.id, idempotency_key="no-appr")


def test_rejected_approval_blocks_execution(db_session: Session) -> None:
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
    service.reject_action(plan.id, action.id, reviewer="bob")
    with pytest.raises(ResolutionValidationError):
        service.execute_action(plan.id, action.id, idempotency_key="rej")


# --- Handlers ---


def test_route_to_review_creates_route(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement", "reason": "Price check"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = _approve_and_execute(service, plan.id, action.id, key="route-1")
    assert execution.execution_status == ExecutionStatus.SUCCEEDED.value
    assert execution.result["status"] == "created"
    route_id = UUID(str(execution.result["reference_id"]))
    route = db_session.get(ExceptionReviewRoute, route_id)
    assert route is not None
    assert route.reconciliation_exception_id == exc.id
    assert route.review_queue == "procurement"
    assert route.proposed_action_id == action.id


def test_route_to_review_replay_does_not_duplicate(db_session: Session) -> None:
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
    first = _approve_and_execute(service, plan.id, action.id, key="route-dup")
    replay = service.execute_action(plan.id, action.id, idempotency_key="route-dup")
    assert replay.id == first.id
    count = db_session.scalar(select(func.count()).select_from(ExceptionReviewRoute))
    assert count == 1


def test_route_to_review_optional_m5_link(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    doc = Document(
        original_filename="inv.pdf",
        stored_filename="inv-stored.pdf",
        document_type=DocumentType.INVOICE.value,
        mime_type="application/pdf",
        file_extension=".pdf",
        file_size=10,
        sha256=uuid4().hex + uuid4().hex,
        storage_path="docs/inv.pdf",
        status=DocumentStatus.EXTRACTED.value,
    )
    db_session.add(doc)
    db_session.flush()
    extraction = DocumentExtractionResult(
        document_id=doc.id,
        detected_type=DocumentType.INVOICE.value,
        outcome=ExtractionOutcome.REVIEW_REQUIRED.value,
        candidate={"invoice_number": "INV-1"},
        evidence=[],
        message="needs review",
    )
    db_session.add(extraction)
    db_session.flush()

    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {
                    "review_queue": "extraction",
                    "document_id": str(doc.id),
                    "extraction_result_id": str(extraction.id),
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = _approve_and_execute(service, plan.id, action.id, key="route-m5")
    route = db_session.get(ExceptionReviewRoute, UUID(str(execution.result["reference_id"])))
    assert route is not None
    assert route.review_task_id is not None


def test_vendor_clarification_creates_request(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    vendor = _seed_vendor(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {
                    "question": "Please confirm unit price",
                    "vendor_id": str(vendor.id),
                    "fields": ["unit_price"],
                    "due_date": "2026-10-01",
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = _approve_and_execute(service, plan.id, action.id, key="vend-1")
    req = db_session.get(
        VendorClarificationRequest, UUID(str(execution.result["reference_id"]))
    )
    assert req is not None
    assert req.vendor_id == vendor.id
    assert req.question.startswith("Please confirm")
    assert req.status == WorkflowRequestStatus.PENDING.value
    assert req.due_date == date(2026, 10, 1)
    assert req.reconciliation_exception_id == exc.id


def test_vendor_clarification_replay_idempotent(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {
                    "question": "Clarify tax",
                    "vendor_reference": "ACME",
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    _approve_and_execute(service, plan.id, action.id, key="vend-dup")
    service.execute_action(plan.id, action.id, idempotency_key="vend-dup")
    assert db_session.scalar(select(func.count()).select_from(VendorClarificationRequest)) == 1


def test_missing_document_creates_request(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {
                    "document_type": "GRN",
                    "reason": "Goods receipt not on file",
                    "vendor_reference": "ACME",
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = _approve_and_execute(service, plan.id, action.id, key="miss-1")
    req = db_session.get(MissingDocumentRequest, UUID(str(execution.result["reference_id"])))
    assert req is not None
    assert req.document_type == "GRN"
    assert req.reconciliation_exception_id == exc.id


def test_missing_document_replay_idempotent(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {"document_type": "PO", "reason": "Missing PO"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    _approve_and_execute(service, plan.id, action.id, key="miss-dup")
    service.execute_action(plan.id, action.id, idempotency_key="miss-dup")
    assert db_session.scalar(select(func.count()).select_from(MissingDocumentRequest)) == 1


def test_escalate_creates_escalation(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {
                    "reason": "High value variance",
                    "priority": EscalationPriority.HIGH.value,
                    "destination": "AP_MANAGER",
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    execution = _approve_and_execute(service, plan.id, action.id, key="esc-1")
    row = db_session.get(ManagerEscalation, UUID(str(execution.result["reference_id"])))
    assert row is not None
    assert row.priority == EscalationPriority.HIGH.value
    assert row.destination == "AP_MANAGER"
    assert row.reconciliation_exception_id == exc.id


def test_escalate_replay_idempotent(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {"reason": "Escalate"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    _approve_and_execute(service, plan.id, action.id, key="esc-dup")
    service.execute_action(plan.id, action.id, idempotency_key="esc-dup")
    assert db_session.scalar(select(func.count()).select_from(ManagerEscalation)) == 1


# --- Execution / idempotency ---


def test_different_key_after_success_blocked(db_session: Session) -> None:
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
    _approve_and_execute(service, plan.id, action.id, key="key-a")
    with pytest.raises(ResolutionValidationError, match="already has an active"):
        service.execute_action(plan.id, action.id, idempotency_key="key-b")
    assert db_session.scalar(select(func.count()).select_from(ExceptionReviewRoute)) == 1


def test_failed_execution_retry(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {
                    "question": "Why?",
                    "vendor_id": str(uuid4()),  # nonexistent → handler failure
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="alice")
    with pytest.raises(ResolutionValidationError, match="Vendor .* was not found"):
        service.execute_action(plan.id, action.id, idempotency_key="fail-1")

    db_session.refresh(action)
    assert action.status == ProposedActionStatus.FAILED.value
    assert db_session.scalar(select(func.count()).select_from(VendorClarificationRequest)) == 0

    # Fix parameters conceptually by creating a new plan action with valid vendor —
    # for retry of same action we need vendor to exist; update stored params.
    vendor = _seed_vendor(db_session)
    action.parameters = {
        "question": "Why?",
        "vendor_id": str(vendor.id),
    }
    db_session.flush()

    retry = service.execute_action(plan.id, action.id, idempotency_key="fail-2")
    assert retry.execution_status == ExecutionStatus.SUCCEEDED.value
    assert db_session.scalar(select(func.count()).select_from(VendorClarificationRequest)) == 1


def test_cancelled_plan_blocked(db_session: Session) -> None:
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
    service.approve_action(plan.id, action.id, reviewer="alice")
    plan.status = ResolutionPlanStatus.CANCELLED.value
    db_session.flush()
    with pytest.raises(ResolutionValidationError, match="CANCELLED"):
        service.execute_action(plan.id, action.id, idempotency_key="cancel-1")


def test_execute_api_endpoint(api_client: TestClient, db_session: Session) -> None:
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
    api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/approve",
        json={"reviewer": "alice"},
    )
    # Approval must not execute.
    assert api_client.get(f"/resolution-plans/{plan.id}/executions").json()["count"] == 0

    resp = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/execute",
        json={"idempotency_key": "api-exec-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["execution_status"] == ExecutionStatus.SUCCEEDED.value
    assert body["result"]["status"] == "created"
    assert body["result"]["reference_id"] is not None


def test_m2_exception_unchanged_after_handler(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    before = exc.status
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {"reason": "Escalate"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    _approve_and_execute(service, plan.id, action.id, key="m2-safe")
    db_session.refresh(exc)
    assert exc.status == before
    assert exc.message == "Invoice unit price exceeds PO"


def test_security_arbitrary_payloads_rejected() -> None:
    for payload in (
        {"action_type": "execute_sql", "parameters": {"sql": "SELECT 1"}},
        {"action_type": "shell", "parameters": {"cmd": "ls"}},
        {"action_type": "http_get", "parameters": {"url": "https://evil.example"}},
        {"action_type": "MODIFY_INVOICE", "parameters": {"amount": "0"}},
    ):
        with pytest.raises((ValidationError, ValueError)):
            from app.resolution.contracts import parse_action_request

            parse_action_request(payload)
