"""M10.2 read-only dashboard summary."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentExtractionResult,
    Invoice,
    ReconciliationException,
    ReviewTask,
    RiskProfileRecord,
    Vendor,
)
from app.db.session import get_db
from app.main import app


def _client(db_session: Session) -> TestClient:
    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def test_dashboard_summary_empty(db_session: Session) -> None:
    client = _client(db_session)
    try:
        response = client.get("/dashboard/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["documents"]["total"] == 0
        assert body["open_exception_count"] == 0
        assert body["pending_review_count"] == 0
        assert body["high_or_critical_risk_count"] == 0
        assert body["open_exceptions"] == []
        assert body["latest_risk_profiles"] == []
        assert body["pending_reviews"] == []
        assert body["recent_activity"] == []
        assert "not fraud probabilities" in body["risk_note"]
        assert "matched total" in body["reconciliation_note"]
        assert "storage_path" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_dashboard_summary_reads_persisted_rows_without_mutation(db_session: Session) -> None:
    vendor = Vendor(name="Dashboard Vendor")
    db_session.add(vendor)
    db_session.flush()
    invoice = Invoice(
        invoice_number="INV-DASH-1",
        vendor_id=vendor.id,
        invoice_date=date(2026, 9, 1),
        currency="INR",
    )
    document = Document(
        original_filename="vendor-invoice.pdf",
        stored_filename="stored.pdf",
        document_type="INVOICE",
        mime_type="application/pdf",
        file_extension=".pdf",
        file_size=12,
        sha256="d" * 64,
        storage_path="storage/secret-path",
        status="REVIEW_REQUIRED",
    )
    db_session.add_all([invoice, document])
    db_session.flush()
    extraction = DocumentExtractionResult(
        document_id=document.id,
        detected_type="INVOICE",
        outcome="REVIEW_REQUIRED",
    )
    db_session.add(extraction)
    db_session.flush()
    task = ReviewTask(
        document_id=document.id,
        extraction_result_id=extraction.id,
        status="PENDING",
        priority="HIGH",
        reason="Amount needs a human check",
    )
    exception = ReconciliationException(
        exception_type="PRICE_MISMATCH",
        severity="HIGH",
        message="Invoice unit price differs from the purchase order.",
        status="OPEN",
        invoice_id=invoice.id,
        fingerprint="dash-ex-1",
        evidence={},
        source_document_ids=[],
    )
    entity_id = uuid4()
    older = RiskProfileRecord(
        entity_type="INVOICE",
        entity_id=entity_id,
        score=90,
        risk_band="CRITICAL",
        score_version="m9.3-v1",
        as_of=date(2026, 1, 1),
        calculated_at=datetime(2026, 1, 1, tzinfo=UTC),
        signal_count=2,
        breakdown={},
        fingerprint="dash-risk-old",
    )
    latest = RiskProfileRecord(
        entity_type="INVOICE",
        entity_id=entity_id,
        score=8,
        risk_band="LOW",
        score_version="m9.3-v1",
        as_of=date(2026, 9, 1),
        calculated_at=datetime(2026, 9, 1, tzinfo=UTC),
        signal_count=1,
        breakdown={},
        fingerprint="dash-risk-new",
    )
    db_session.add_all([task, exception, older, latest])
    db_session.flush()
    before = db_session.scalar(select(func.count()).select_from(RiskProfileRecord))

    client = _client(db_session)
    try:
        response = client.get("/dashboard/summary")
        assert response.status_code == 200
        body = response.json()
        assert body["documents"]["total"] == 1
        assert body["documents"]["counts"]["REVIEW_REQUIRED"] == 1
        assert body["open_exception_count"] == 1
        assert body["reconciliation_exceptions"]["counts"]["OPEN"] == 1
        assert body["open_exceptions"][0]["exception_type"] == "PRICE_MISMATCH"
        assert body["open_exceptions"][0]["invoice_number"] == "INV-DASH-1"
        assert body["pending_review_count"] == 1
        assert body["pending_reviews"][0]["document_filename"] == "vendor-invoice.pdf"
        assert body["risk_profiles"]["total"] == 1
        assert body["risk_profiles"]["counts"]["LOW"] == 1
        assert body["risk_profiles"]["counts"]["CRITICAL"] == 0
        assert body["high_or_critical_risk_count"] == 0
        assert body["latest_risk_profiles"][0]["score"] == 8
        assert "storage/secret-path" not in response.text
        after = db_session.scalar(select(func.count()).select_from(RiskProfileRecord))
        assert after == before
    finally:
        app.dependency_overrides.clear()
