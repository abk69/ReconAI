"""M8.1 — Agentic resolution architecture and persistence foundation."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import (
    ActionApproval,
    ActionExecution,
    PolicyGroundingResult,
    ProposedAction,
    ReconciliationException,
    ResolutionPlan,
)
from app.db.session import get_db
from app.domain.enums import (
    ActionType,
    ApprovalDecision,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ExecutionStatus,
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.main import app
from app.resolution.contracts import parse_action_parameters, parse_action_request
from app.resolution.guardrails import GuardrailError, validate_action, validate_approval
from app.resolution.registry import ActionRegistry, build_default_registry
from app.resolution.transitions import (
    EXECUTION_ALLOWED_TRANSITIONS,
    InvalidResolutionTransitionError,
    assert_execution_transition,
)
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


def _seed_exception(
    session: Session,
    *,
    status: str = ExceptionStatus.OPEN.value,
) -> ReconciliationException:
    exc = ReconciliationException(
        exception_type=ExceptionType.PRICE_MISMATCH.value,
        severity=ExceptionSeverity.HIGH.value,
        message="Invoice unit price exceeds PO",
        status=status,
        evidence={"po_price": "10.00", "invoice_price": "12.00"},
        fingerprint=f"fp-{uuid4()}",
    )
    session.add(exc)
    session.flush()
    return exc


def _seed_grounding(
    session: Session,
    exception_id,
) -> PolicyGroundingResult:
    row = PolicyGroundingResult(
        reconciliation_exception_id=exception_id,
        status="SUPPORTED",
        conclusion="Price variance may require approval.",
        explanation="Policy allows variance review.",
        policy_support="Section 4.2",
        limitations="",
        citations=[],
        retrieved_chunk_ids=[],
        retrieval_query="price mismatch",
    )
    session.add(row)
    session.flush()
    return row


def test_resolution_plan_creation(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        reasoning_summary="Route for procurement review",
        proposed_by="agent:m8.1",
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
                "rationale": "Human review needed",
            }
        ],
    )
    assert plan.id is not None
    assert plan.status == ResolutionPlanStatus.APPROVAL_REQUIRED.value
    assert plan.reasoning_summary == "Route for procurement review"
    assert plan.proposed_by == "agent:m8.1"
    assert len(plan.proposed_actions) == 1


def test_proposed_action_creation(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {
                    "reason": "Invoice price exceeds PO price",
                    "fields": ["unit_price"],
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    assert action.action_type == ActionType.REQUEST_VENDOR_CLARIFICATION.value
    assert action.parameters["fields"] == ["unit_price"]
    assert action.requires_approval is True
    assert action.status == ProposedActionStatus.PENDING.value


def test_multiple_actions_maintain_deterministic_order(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {"document_type": "GRN"},
            },
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            },
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {
                    "manager_role": "AP_MANAGER",
                    "summary": "Escalate after review",
                },
            },
        ],
    )
    ordered = service.list_actions(plan.id)
    assert [a.action_order for a in ordered] == [0, 1, 2]
    assert [a.action_type for a in ordered] == [
        ActionType.REQUEST_MISSING_DOCUMENT.value,
        ActionType.ROUTE_TO_REVIEW.value,
        ActionType.ESCALATE_TO_MANAGER.value,
    ]


def test_action_parameters_validate_against_action_type() -> None:
    parsed = parse_action_parameters(
        ActionType.ROUTE_TO_REVIEW,
        {"review_queue": "procurement"},
    )
    assert parsed.model_dump() == {"review_queue": "procurement"}

    with pytest.raises(ValidationError):
        parse_action_parameters(ActionType.ROUTE_TO_REVIEW, {"reason": "wrong shape"})


def test_unknown_action_types_are_rejected(db_session: Session) -> None:
    with pytest.raises((ValidationError, ValueError)):
        parse_action_request(
            {
                "action_type": "MODIFY_INVOICE",
                "parameters": {},
            }
        )

    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    with pytest.raises((ValidationError, ValueError, ResolutionValidationError)):
        service.create_plan(
            reconciliation_exception_id=exc.id,
            actions=[
                {
                    "action_type": "DELETE_TRANSACTION",
                    "parameters": {},
                }
            ],
        )


def test_approval_records_are_persisted(db_session: Session) -> None:
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
    approval = service.approve_action(
        plan.id,
        action.id,
        reviewer="alice@example.com",
        reason="Looks correct",
    )
    assert approval.decision == ApprovalDecision.APPROVED.value
    assert approval.reviewer == "alice@example.com"
    stored = db_session.get(ActionApproval, approval.id)
    assert stored is not None
    assert stored.reason == "Looks correct"
    db_session.refresh(action)
    assert action.status == ProposedActionStatus.APPROVED.value


def test_rejected_actions_cannot_execute(db_session: Session) -> None:
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
    service.reject_action(plan.id, action.id, reviewer="bob", reason="Not needed")
    with pytest.raises(ResolutionValidationError, match="REJECTED|reject"):
        service.execute_action(plan.id, action.id, idempotency_key="rej-1")


def test_approval_required_cannot_execute_without_approval(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {
                    "manager_role": "AP_MANAGER",
                    "summary": "Need escalation",
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    with pytest.raises(ResolutionValidationError, match="Approval-required"):
        service.execute_action(plan.id, action.id, idempotency_key="no-appr-1")


def test_idempotency_key_uniqueness_enforced(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
                "requires_approval": False,
            }
        ],
        commit=True,
    )
    action = plan.proposed_actions[0]
    first = ActionExecution(
        proposed_action_id=action.id,
        execution_status=ExecutionStatus.SUCCEEDED.value,
        idempotency_key="same-key",
        result={"ok": True},
    )
    db_session.add(first)
    db_session.flush()

    duplicate = ActionExecution(
        proposed_action_id=action.id,
        execution_status=ExecutionStatus.PENDING.value,
        idempotency_key="same-key",
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_duplicate_execution_attempts_rejected_safely(db_session: Session) -> None:
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
    first = service.execute_action(plan.id, action.id, idempotency_key="dup-key")
    replay = service.execute_action(plan.id, action.id, idempotency_key="dup-key")
    assert replay.id == first.id
    assert first.execution_status == ExecutionStatus.SUCCEEDED.value

    with pytest.raises(ResolutionValidationError, match="already has an active"):
        service.execute_action(plan.id, action.id, idempotency_key="different-key")


def test_execution_status_transitions_are_valid() -> None:
    assert ExecutionStatus.SUCCEEDED in EXECUTION_ALLOWED_TRANSITIONS[ExecutionStatus.RUNNING]
    assert ExecutionStatus.RUNNING not in EXECUTION_ALLOWED_TRANSITIONS[ExecutionStatus.SUCCEEDED]
    assert_execution_transition(ExecutionStatus.PENDING, ExecutionStatus.RUNNING)
    with pytest.raises(InvalidResolutionTransitionError):
        assert_execution_transition(ExecutionStatus.SUCCEEDED, ExecutionStatus.RUNNING)


def test_audit_relationships_remain_intact(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    grounding = _seed_grounding(db_session, exc.id)
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        policy_grounding_result_id=grounding.id,
        proposed_by="agent:m8.1",
        reasoning_summary="Grounded proposal",
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
                "rationale": "Policy supports review",
            }
        ],
    )
    action = plan.proposed_actions[0]
    approval = service.approve_action(plan.id, action.id, reviewer="alice", reason="ok")
    execution = service.execute_action(plan.id, action.id, idempotency_key="audit-1")

    # Exception delete blocked while plan exists (RESTRICT).
    db_session.delete(exc)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    reloaded = db_session.get(ResolutionPlan, plan.id)
    assert reloaded is not None
    assert reloaded.policy_grounding_result_id == grounding.id
    assert reloaded.proposed_by == "agent:m8.1"
    assert db_session.get(ActionApproval, approval.id) is not None
    assert db_session.get(ActionExecution, execution.id) is not None
    assert db_session.get(ReconciliationException, exc.id) is not None


def test_api_endpoints_work(api_client: TestClient, db_session: Session) -> None:
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

    get_plan = api_client.get(f"/resolution-plans/{plan.id}")
    assert get_plan.status_code == 200
    body = get_plan.json()
    assert body["status"] == ResolutionPlanStatus.APPROVAL_REQUIRED.value
    assert len(body["actions"]) == 1

    actions = api_client.get(f"/resolution-plans/{plan.id}/actions")
    assert actions.status_code == 200
    assert actions.json()["count"] == 1

    approve = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/approve",
        json={"reviewer": "alice", "reason": "approved"},
    )
    assert approve.status_code == 200
    assert approve.json()["decision"] == ApprovalDecision.APPROVED.value

    # Approval must not silently execute.
    executions = api_client.get(f"/resolution-plans/{plan.id}/executions")
    assert executions.status_code == 200
    assert executions.json()["count"] == 0

    reject_plan_exc = _seed_exception(db_session)
    reject_plan = service.create_plan(
        reconciliation_exception_id=reject_plan_exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {"document_type": "PO"},
            }
        ],
    )
    reject_action_id = reject_plan.proposed_actions[0].id
    reject = api_client.post(
        f"/resolution-plans/{reject_plan.id}/actions/{reject_action_id}/reject",
        json={"reviewer": "bob", "reason": "no"},
    )
    assert reject.status_code == 200
    assert reject.json()["decision"] == ApprovalDecision.REJECTED.value


def test_m2_reconciliation_records_unchanged(db_session: Session) -> None:
    exc = _seed_exception(db_session, status=ExceptionStatus.OPEN.value)
    original_message = exc.message
    original_evidence = dict(exc.evidence)
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
    service.execute_action(plan.id, action.id, idempotency_key="m2-safe")

    db_session.refresh(exc)
    assert exc.status == ExceptionStatus.OPEN.value
    assert exc.message == original_message
    assert exc.evidence == original_evidence


def test_m7_grounding_records_unchanged(db_session: Session) -> None:
    exc = _seed_exception(db_session)
    grounding = _seed_grounding(db_session, exc.id)
    before = {
        "status": grounding.status,
        "conclusion": grounding.conclusion,
        "explanation": grounding.explanation,
    }
    service = ResolutionService(db_session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        policy_grounding_result_id=grounding.id,
        actions=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="alice")
    service.execute_action(plan.id, action.id, idempotency_key="m7-safe")

    db_session.refresh(grounding)
    assert grounding.status == before["status"]
    assert grounding.conclusion == before["conclusion"]
    assert grounding.explanation == before["explanation"]
    count = db_session.scalars(select(PolicyGroundingResult)).all()
    assert len(count) == 1


def test_transaction_rollback_works(db_session: Session) -> None:
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
        commit=False,
    )
    action = plan.proposed_actions[0]
    action_id = action.id
    plan_id = plan.id
    service.approve_action(plan.id, action.id, reviewer="alice", commit=False)
    db_session.flush()
    db_session.rollback()

    assert db_session.get(ResolutionPlan, plan_id) is None
    assert db_session.get(ProposedAction, action_id) is None


def test_action_registry_returns_only_explicitly_registered_actions() -> None:
    registry = build_default_registry()
    available = registry.list_available()
    assert available == [
        ActionType.ESCALATE_TO_MANAGER,
        ActionType.REQUEST_MISSING_DOCUMENT,
        ActionType.REQUEST_VENDOR_CLARIFICATION,
        ActionType.ROUTE_TO_REVIEW,
    ]
    assert not registry.is_registered("MODIFY_INVOICE")
    assert not registry.is_registered("APPROVE_PAYMENT")

    empty = ActionRegistry()
    assert empty.list_available() == []


def test_guardrails_reject_cancelled_plan(db_session: Session) -> None:
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
    plan.status = ResolutionPlanStatus.CANCELLED.value
    db_session.flush()
    action = plan.proposed_actions[0]
    with pytest.raises(GuardrailError, match="CANCELLED"):
        validate_action(action, plan=plan, registry=service.registry)


def test_guardrails_validate_approval_latest_decision(db_session: Session) -> None:
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
    earlier = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    later_ts = datetime(2026, 1, 2, 12, 0, 0, tzinfo=UTC)
    # Normalize the first approval timestamp so the superseding row is clearly later.
    first = db_session.scalars(
        select(ActionApproval).where(ActionApproval.proposed_action_id == action.id)
    ).one()
    first.created_at = earlier
    first.decided_at = earlier
    later = ActionApproval(
        proposed_action_id=action.id,
        decision=ApprovalDecision.REJECTED.value,
        reviewer="bob",
        reason="changed mind",
        decided_at=later_ts,
        created_at=later_ts,
    )
    db_session.add(later)
    db_session.flush()
    db_session.expire_all()
    action = service.get_action(plan.id, action.id)
    assert len(action.approvals) == 2
    with pytest.raises(GuardrailError, match="REJECTED"):
        validate_approval(action, list(action.approvals))
