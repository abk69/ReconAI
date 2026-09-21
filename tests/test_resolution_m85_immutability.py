"""M8.5 hardening — approved ProposedAction parameter immutability."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.db.models import ReconciliationException
from app.domain.enums import (
    ActionType,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ExecutionStatus,
    ProposedActionStatus,
)
from app.resolution.immutability import (
    ProposedActionImmutabilityError,
    compute_parameters_hash,
)
from app.services.resolution_execution_service import (
    ResolutionExecutionService,
    ResolutionExecutionValidationError,
)
from app.services.resolution_service import ResolutionService


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


def test_parameters_cannot_mutate_after_approval(db_session: Session) -> None:
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
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    db_session.refresh(action)
    action.parameters = {"review_queue": "finance"}
    with pytest.raises(ProposedActionImmutabilityError, match="parameters"):
        db_session.flush()
    db_session.rollback()


def test_action_type_cannot_mutate_after_approval(db_session: Session) -> None:
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
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    db_session.refresh(action)
    action.action_type = ActionType.ESCALATE_TO_MANAGER.value
    with pytest.raises(ProposedActionImmutabilityError, match="action_type"):
        db_session.flush()
    db_session.rollback()


def test_parameter_hash_created_at_approval(db_session: Session) -> None:
    service = ResolutionService(db_session)
    params = {"review_queue": "procurement"}
    plan = service.create_plan(
        reconciliation_exception_id=_seed_exception(db_session).id,
        actions=[{"action_type": ActionType.ROUTE_TO_REVIEW, "parameters": params}],
    )
    action = plan.proposed_actions[0]
    assert action.approved_parameters_hash is None
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    db_session.refresh(action)
    assert action.approved_parameters_hash == compute_parameters_hash(params)


def test_execution_succeeds_when_hash_matches(db_session: Session) -> None:
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
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    execution = service.execute_action(plan.id, action.id, idempotency_key="hash-ok")
    assert execution.execution_status == ExecutionStatus.SUCCEEDED.value


def test_execution_rejects_when_hash_differs(db_session: Session) -> None:
    from sqlalchemy import update

    from app.db.models import ProposedAction

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
    service.approve_action(plan.id, action.id, reviewer="alice@example.com")
    # Simulate out-of-band hash tampering (bypasses ORM attribute guards).
    db_session.execute(
        update(ProposedAction)
        .where(ProposedAction.id == action.id)
        .values(approved_parameters_hash="0" * 64)
    )
    db_session.expire(action)
    with pytest.raises(ResolutionExecutionValidationError, match="approved_parameters_hash"):
        ResolutionExecutionService(db_session).execute_action(
            plan.id,
            action.id,
            idempotency_key="hash-bad",
        )


def test_rejected_actions_remain_protected(db_session: Session) -> None:
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
    service.reject_action(plan.id, action.id, reviewer="bob@example.com")
    db_session.refresh(action)
    assert action.status == ProposedActionStatus.REJECTED.value
    action.parameters = {"review_queue": "other"}
    with pytest.raises(ProposedActionImmutabilityError, match="parameters"):
        db_session.flush()
    db_session.rollback()
    db_session.refresh(action)
    action.action_type = ActionType.ESCALATE_TO_MANAGER.value
    with pytest.raises(ProposedActionImmutabilityError, match="action_type"):
        db_session.flush()
    db_session.rollback()
