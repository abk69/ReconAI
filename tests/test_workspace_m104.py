"""M10.4 read endpoints for review, grounding, and resolution plans."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import (
    ActionApproval,
    PolicyGroundingResult,
    ProposedAction,
    ReconciliationException,
    ResolutionPlan,
)
from app.db.session import get_db
from app.main import app


def _client(db_session: Session) -> TestClient:
    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_review_and_resolution_lists_empty(db_session: Session) -> None:
    client = _client(db_session)
    try:
        review = client.get("/review/tasks", params={"limit": 25, "offset": 0})
        assert review.status_code == 200
        assert review.json()["total"] == 0
        assert review.json()["count"] == 0

        plans = client.get("/resolution-plans")
        assert plans.status_code == 200
        assert plans.json()["total"] == 0
        assert plans.json()["items"] == []
    finally:
        app.dependency_overrides.clear()


def test_policy_grounding_and_resolution_reads(db_session: Session) -> None:
    exception = ReconciliationException(
        exception_type="QUANTITY_MISMATCH",
        severity="HIGH",
        message="Invoice quantity exceeds received quantity.",
        status="OPEN",
        fingerprint="m104-ex-1",
        evidence={"expected_quantity": "2", "actual_quantity": "5"},
        source_document_ids=[],
    )
    db_session.add(exception)
    db_session.flush()
    recorded_at = datetime(2026, 9, 23, 12, 0, tzinfo=UTC)
    grounding = PolicyGroundingResult(
        reconciliation_exception_id=exception.id,
        status="INSUFFICIENT_EVIDENCE",
        conclusion="Policy text does not settle the quantity gap.",
        explanation="Retrieved chunks do not state a quantity tolerance.",
        policy_support="",
        limitations="No matching policy clause.",
        citations=[
            {
                "policy_version_label": "v1",
                "section_title": "Receipts",
                "source_filename": "policy.pdf",
                "chunk_id": "11111111-1111-1111-1111-111111111111",
            }
        ],
        retrieved_chunk_ids=[],
        retrieval_query="quantity mismatch",
        model="gemini-test",
        provider_metadata={"api_key": "should-not-leak"},
        created_at=recorded_at,
    )
    db_session.add(grounding)
    db_session.flush()
    plan = ResolutionPlan(
        reconciliation_exception_id=exception.id,
        status="APPROVAL_REQUIRED",
        reasoning_summary="Route the quantity gap to a reviewer.",
        proposed_by="planner",
        planner_model="gemini-test",
        limitations="Does not change invoice quantities.",
        policy_grounding_result_id=grounding.id,
        created_at=recorded_at,
        updated_at=recorded_at,
    )
    db_session.add(plan)
    db_session.flush()
    action = ProposedAction(
        resolution_plan_id=plan.id,
        action_type="ROUTE_TO_REVIEW",
        action_order=1,
        parameters={"queue": "procurement"},
        rationale="A person should confirm the quantity gap.",
        requires_approval=True,
        status="PENDING",
    )
    db_session.add(action)
    db_session.flush()
    db_session.add(
        ActionApproval(
            proposed_action_id=action.id,
            decision="REJECTED",
            reviewer="casey",
            reason="Need a corrected receipt first.",
            decided_at=recorded_at,
            created_at=recorded_at,
        )
    )
    db_session.flush()

    client = _client(db_session)
    try:
        listed = client.get(
            "/resolution-plans",
            params={
                "status": "APPROVAL_REQUIRED",
                "reconciliation_exception_id": str(exception.id),
            },
        )
        assert listed.status_code == 200
        item = listed.json()["items"][0]
        assert item["exception_type"] == "QUANTITY_MISMATCH"
        assert item["action_count"] == 1
        assert "api_key" not in listed.text

        approvals = client.get(f"/resolution-plans/{plan.id}/approvals")
        assert approvals.status_code == 200
        assert approvals.json()["items"][0]["decision"] == "REJECTED"
        assert approvals.json()["items"][0]["reviewer"] == "casey"

        explained = client.get(f"/reconciliation/exceptions/{exception.id}/policy-grounding")
        assert explained.status_code == 200
        body = explained.json()["items"][0]
        assert body["status"] == "INSUFFICIENT_EVIDENCE"
        assert body["citations"][0]["section_title"] == "Receipts"
        assert "provider_metadata" not in explained.text
        assert "should-not-leak" not in explained.text

        missing = client.get(
            "/reconciliation/exceptions/00000000-0000-0000-0000-000000000000/policy-grounding"
        )
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
