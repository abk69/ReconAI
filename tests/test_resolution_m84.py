"""M8.4 — Human approval gate for resolution actions."""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    ActionApproval,
    ActionExecution,
    ReconciliationException,
)
from app.db.session import get_db
from app.domain.enums import (
    ActionType,
    ApprovalDecision,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ProposedActionStatus,
    ResolutionPlanStatus,
)
from app.main import app
from app.resolution.guardrails import GuardrailError, validate_approval
from app.resolution.registry import build_default_registry
from app.resolution.reviewer import InvalidReviewerError, validate_reviewer
from app.services.resolution_service import (
    ResolutionConflictError,
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


def _plan_with_actions(
    session: Session,
    *,
    action_specs: list[dict],
) -> tuple[ResolutionService, object]:
    exc = _seed_exception(session)
    service = ResolutionService(session)
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        reasoning_summary="M8.4 approval gate test",
        actions=action_specs,
    )
    return service, plan


# ── Reviewer identity ──────────────────────────────────────────────────────


def test_reviewer_required_and_blank_rejected() -> None:
    with pytest.raises(InvalidReviewerError):
        validate_reviewer(None)
    with pytest.raises(InvalidReviewerError):
        validate_reviewer("")
    with pytest.raises(InvalidReviewerError):
        validate_reviewer("   ")
    with pytest.raises(InvalidReviewerError):
        validate_reviewer("bad; DROP TABLE--")
    assert validate_reviewer("  alice@example.com  ") == "alice@example.com"


# ── Approve / reject ───────────────────────────────────────────────────────


def test_approve_pending_action(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
                "rationale": "needs review",
            }
        ],
    )
    action = plan.proposed_actions[0]
    approval = service.approve_action(
        plan.id,
        action.id,
        reviewer="reviewer@example.com",
        comment="Reviewed exception and supporting evidence.",
    )
    assert approval.decision == ApprovalDecision.APPROVED.value
    assert approval.reviewer == "reviewer@example.com"
    assert approval.reason == "Reviewed exception and supporting evidence."
    db_session.refresh(action)
    db_session.refresh(plan)
    assert action.status == ProposedActionStatus.APPROVED.value
    assert plan.status == ResolutionPlanStatus.APPROVED.value
    # Approval must not execute
    assert db_session.scalars(
        select(ActionExecution).where(ActionExecution.proposed_action_id == action.id)
    ).first() is None


def test_reject_pending_action(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {
                    "document_type": "PACKING_SLIP",
                    "reason": "Missing packing slip",
                },
            }
        ],
    )
    action = plan.proposed_actions[0]
    approval = service.reject_action(
        plan.id,
        action.id,
        reviewer="reviewer@example.com",
        comment="Need additional vendor evidence.",
    )
    assert approval.decision == ApprovalDecision.REJECTED.value
    db_session.refresh(action)
    db_session.refresh(plan)
    assert action.status == ProposedActionStatus.REJECTED.value
    assert plan.status == ResolutionPlanStatus.REJECTED.value


def test_blank_reviewer_rejected_by_service(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    with pytest.raises(ResolutionValidationError, match="reviewer"):
        service.approve_action(plan.id, action.id, reviewer="   ")


def test_action_must_belong_to_plan(db_session: Session) -> None:
    service, plan_a = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "a"},
            }
        ],
    )
    _, plan_b = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "b"},
            }
        ],
    )
    action_b = plan_b.proposed_actions[0]
    with pytest.raises(Exception, match="not found"):
        service.approve_action(plan_a.id, action_b.id, reviewer="alice@example.com")


def test_cancelled_plan_rejected(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    plan.status = ResolutionPlanStatus.CANCELLED.value
    db_session.flush()
    with pytest.raises(ResolutionValidationError, match="cancelled"):
        service.approve_action(plan.id, action.id, reviewer="alice@example.com")


# ── State transitions ──────────────────────────────────────────────────────


def test_pending_to_approved_and_rejected(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    assert action.status == ProposedActionStatus.PENDING.value
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    db_session.refresh(action)
    assert action.status == ProposedActionStatus.APPROVED.value


def test_rejected_cannot_become_approved(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.reject_action(plan.id, action.id, reviewer="bob@example.com")
    with pytest.raises(ResolutionValidationError, match="Cannot transition|status"):
        service.approve_action(plan.id, action.id, reviewer="alice@example.com")


def test_completed_cannot_be_approved(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    action.status = ProposedActionStatus.COMPLETED.value
    db_session.flush()
    with pytest.raises(ResolutionValidationError, match="COMPLETED"):
        service.approve_action(plan.id, action.id, reviewer="alice@example.com")


def test_executing_cannot_be_approved(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    action.status = ProposedActionStatus.EXECUTING.value
    db_session.flush()
    with pytest.raises(ResolutionValidationError, match="EXECUTING"):
        service.approve_action(plan.id, action.id, reviewer="alice@example.com")


# ── Duplicate decisions ────────────────────────────────────────────────────


def test_duplicate_approval_is_idempotent(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    first = service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    second = service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    assert first.id == second.id
    rows = list(
        db_session.scalars(
            select(ActionApproval).where(ActionApproval.proposed_action_id == action.id)
        ).all()
    )
    assert len(rows) == 1


def test_duplicate_rejection_is_idempotent(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    first = service.reject_action(plan.id, action.id, reviewer="bob@example.com")
    second = service.reject_action(plan.id, action.id, reviewer="bob@example.com")
    assert first.id == second.id
    rows = list(
        db_session.scalars(
            select(ActionApproval).where(ActionApproval.proposed_action_id == action.id)
        ).all()
    )
    assert len(rows) == 1


def test_conflicting_decision_after_approve_rejected(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    with pytest.raises(ResolutionValidationError, match="Cannot transition|status"):
        service.reject_action(plan.id, action.id, reviewer="bob@example.com")


def test_approval_idempotency_key(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    first = service.approve_action(
        plan.id,
        action.id,
        reviewer="alice@example.com",
        idempotency_key="appr-key-1",
    )
    second = service.approve_action(
        plan.id,
        action.id,
        reviewer="alice@example.com",
        idempotency_key="appr-key-1",
    )
    assert first.id == second.id

    # Conflicting decision with same key on a fresh pending action
    service2, plan2 = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {"reason": "Need help", "destination": "AP_MANAGER"},
            }
        ],
    )
    action2 = plan2.proposed_actions[0]
    with pytest.raises(ResolutionConflictError, match="idempotency_key|conflicting"):
        service2.reject_action(
            plan2.id,
            action2.id,
            reviewer="bob@example.com",
            idempotency_key="appr-key-1",
        )


# ── Multi-action plans ─────────────────────────────────────────────────────


def test_multi_action_one_pending_stays_approval_required(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.REQUEST_MISSING_DOCUMENT,
                "parameters": {
                    "document_type": "PACKING_SLIP",
                    "reason": "Need packing slip",
                },
                "rationale": "doc",
            },
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
                "rationale": "review",
            },
        ],
    )
    assert plan.status == ResolutionPlanStatus.APPROVAL_REQUIRED.value
    actions = sorted(plan.proposed_actions, key=lambda a: a.action_order)
    assert [a.action_order for a in actions] == [0, 1]

    service.approve_action(plan.id, actions[0].id, reviewer="alice@example.com")
    db_session.refresh(plan)
    assert plan.status == ResolutionPlanStatus.APPROVAL_REQUIRED.value

    service.approve_action(plan.id, actions[1].id, reviewer="alice@example.com")
    db_session.refresh(plan)
    assert plan.status == ResolutionPlanStatus.APPROVED.value


def test_multi_action_one_rejected_keeps_pending_approval_required(
    db_session: Session,
) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
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
    service.reject_action(plan.id, actions[0].id, reviewer="bob@example.com")
    db_session.refresh(plan)
    db_session.refresh(actions[0])
    assert actions[0].status == ProposedActionStatus.REJECTED.value
    assert plan.status == ResolutionPlanStatus.APPROVAL_REQUIRED.value


def test_multi_action_all_rejected_plan_rejected(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
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
    for action in plan.proposed_actions:
        service.reject_action(plan.id, action.id, reviewer="bob@example.com")
    db_session.refresh(plan)
    assert plan.status == ResolutionPlanStatus.REJECTED.value


# ── Security ───────────────────────────────────────────────────────────────


def test_cannot_disable_requires_approval_client_side(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
                "requires_approval": False,
            }
        ],
    )
    action = plan.proposed_actions[0]
    assert action.requires_approval is True
    with pytest.raises(ResolutionValidationError, match="Approval-required"):
        service.execute_action(plan.id, action.id, idempotency_key="bypass-1")


def test_registry_authoritative_even_if_row_flag_cleared(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    action.requires_approval = False
    db_session.flush()
    registry = build_default_registry()
    with pytest.raises(GuardrailError, match="Approval-required"):
        validate_approval(action, list(action.approvals), registry=registry)


def test_cannot_execute_without_approval(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {"reason": "Need help", "destination": "AP_MANAGER"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    with pytest.raises(ResolutionValidationError, match="Approval-required"):
        service.execute_action(plan.id, action.id, idempotency_key="no-appr")


def test_approve_does_not_execute(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    assert (
        db_session.scalars(
            select(ActionExecution).where(ActionExecution.proposed_action_id == action.id)
        ).first()
        is None
    )
    db_session.refresh(action)
    assert action.status == ProposedActionStatus.APPROVED.value


def test_parameters_not_mutated_by_approval(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action = plan.proposed_actions[0]
    original = dict(action.parameters)
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    db_session.refresh(action)
    assert dict(action.parameters) == original


# ── Audit ──────────────────────────────────────────────────────────────────


def test_approval_audit_row_immutable_fields(db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
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
        comment="looks good",
    )
    stored = db_session.get(ActionApproval, approval.id)
    assert stored is not None
    assert stored.reviewer == "alice@example.com"
    assert stored.reason == "looks good"
    assert stored.decided_at is not None
    assert stored.created_at is not None
    # History preserved — duplicate approve returns same row, no overwrite
    again = service.approve_action(plan.id, action.id, reviewer="other@example.com")
    assert again.id == stored.id
    assert again.reviewer == "alice@example.com"


# ── API ────────────────────────────────────────────────────────────────────


def test_api_approve_and_reject(api_client: TestClient, db_session: Session) -> None:
    service, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action_id = plan.proposed_actions[0].id
    db_session.commit()

    approve = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/approve",
        json={
            "reviewer": "reviewer@example.com",
            "comment": "Reviewed exception and supporting evidence.",
            "idempotency_key": "api-appr-1",
        },
    )
    assert approve.status_code == 200, approve.text
    body = approve.json()
    assert body["plan_id"] == str(plan.id)
    assert body["action_id"] == str(action_id)
    assert body["action_type"] == ActionType.ROUTE_TO_REVIEW.value
    assert body["action_status"] == ProposedActionStatus.APPROVED.value
    assert body["plan_status"] == ResolutionPlanStatus.APPROVED.value
    assert body["decision"] == ApprovalDecision.APPROVED.value
    assert body["reviewer"] == "reviewer@example.com"
    assert body["comment"] == "Reviewed exception and supporting evidence."
    assert body["approval_id"]
    assert body["decided_at"]
    assert body["reused_existing"] is False

    # No executions created by approve
    executions = api_client.get(f"/resolution-plans/{plan.id}/executions")
    assert executions.status_code == 200
    assert executions.json()["count"] == 0

    # Reject path on a fresh plan
    service2, plan2 = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ESCALATE_TO_MANAGER,
                "parameters": {"reason": "Need help", "destination": "AP_MANAGER"},
            }
        ],
    )
    reject_id = plan2.proposed_actions[0].id
    db_session.commit()
    reject = api_client.post(
        f"/resolution-plans/{plan2.id}/actions/{reject_id}/reject",
        json={
            "reviewer": "reviewer@example.com",
            "comment": "Need additional vendor evidence.",
        },
    )
    assert reject.status_code == 200, reject.text
    assert reject.json()["decision"] == ApprovalDecision.REJECTED.value
    assert reject.json()["action_status"] == ProposedActionStatus.REJECTED.value
    assert reject.json()["plan_status"] == ResolutionPlanStatus.REJECTED.value


def test_api_blank_reviewer_validation(api_client: TestClient, db_session: Session) -> None:
    _, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action_id = plan.proposed_actions[0].id
    db_session.commit()
    resp = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/approve",
        json={"reviewer": "   ", "comment": "x"},
    )
    assert resp.status_code == 422


def test_api_wrong_plan_action_ownership(api_client: TestClient, db_session: Session) -> None:
    _, plan_a = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "a"},
            }
        ],
    )
    _, plan_b = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "b"},
            }
        ],
    )
    action_b = plan_b.proposed_actions[0].id
    db_session.commit()
    resp = api_client.post(
        f"/resolution-plans/{plan_a.id}/actions/{action_b}/approve",
        json={"reviewer": "alice@example.com", "comment": "nope"},
    )
    assert resp.status_code == 404


def test_api_unknown_action(api_client: TestClient, db_session: Session) -> None:
    _, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    db_session.commit()
    resp = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{uuid4()}/approve",
        json={"reviewer": "alice@example.com", "comment": "nope"},
    )
    assert resp.status_code == 404


def test_api_duplicate_approve_idempotent(api_client: TestClient, db_session: Session) -> None:
    _, plan = _plan_with_actions(
        db_session,
        action_specs=[
            {
                "action_type": ActionType.ROUTE_TO_REVIEW,
                "parameters": {"review_queue": "procurement"},
            }
        ],
    )
    action_id = plan.proposed_actions[0].id
    db_session.commit()
    payload = {
        "reviewer": "alice@example.com",
        "comment": "ok",
        "idempotency_key": "dup-api-1",
    }
    first = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/approve",
        json=payload,
    )
    second = api_client.post(
        f"/resolution-plans/{plan.id}/actions/{action_id}/approve",
        json=payload,
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["approval_id"] == second.json()["approval_id"]
    assert second.json()["reused_existing"] is True
