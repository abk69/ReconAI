"""M10.5 read-only risk profile and scan queries."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import (
    AnomalyScanJob,
    AnomalySignalRecord,
    Invoice,
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


def test_risk_and_scan_lists_empty(db_session: Session) -> None:
    client = _client(db_session)
    try:
        profiles = client.get("/risk/profiles")
        assert profiles.status_code == 200
        body = profiles.json()
        assert body["total"] == 0
        assert body["counts_by_band"]["LOW"] == 0
        scans = client.get("/anomalies/scans")
        assert scans.status_code == 200
        assert scans.json()["total"] == 0
    finally:
        app.dependency_overrides.clear()


def test_latest_profile_history_and_high_signals(db_session: Session) -> None:
    vendor = Vendor(name="Northwind")
    db_session.add(vendor)
    db_session.flush()
    invoice = Invoice(
        invoice_number="INV-200",
        vendor_id=vendor.id,
        invoice_date=date(2026, 9, 3),
        currency="INR",
        status="OPEN",
        total_amount=Decimal("10"),
    )
    db_session.add(invoice)
    db_session.flush()
    older = datetime(2026, 1, 1, tzinfo=UTC)
    newer = datetime(2026, 9, 1, tzinfo=UTC)
    db_session.add_all(
        [
            RiskProfileRecord(
                entity_type="VENDOR",
                entity_id=vendor.id,
                score=90,
                risk_band="CRITICAL",
                score_version="m9.3-v1",
                as_of=date(2026, 1, 1),
                calculated_at=older,
                signal_count=4,
                breakdown={"contributing_signals": [], "type_breakdown": []},
                fingerprint="m105-old",
                created_at=older,
            ),
            RiskProfileRecord(
                entity_type="VENDOR",
                entity_id=vendor.id,
                score=12,
                risk_band="LOW",
                score_version="m9.3-v1",
                as_of=date(2026, 9, 1),
                calculated_at=newer,
                signal_count=1,
                breakdown={
                    "contributing_signals": [
                        {
                            "anomaly_type": "PRICE_VARIANCE",
                            "severity": "LOW",
                            "base_weight": "10",
                            "severity_multiplier": "1",
                            "recency_multiplier": "1",
                            "raw_contribution": "10",
                            "capped_contribution": None,
                            "signal_id": "22222222-2222-2222-2222-222222222222",
                        }
                    ]
                },
                fingerprint="m105-new",
                created_at=newer,
            ),
            RiskProfileRecord(
                entity_type="INVOICE",
                entity_id=invoice.id,
                score=30,
                risk_band="MEDIUM",
                score_version="m9.3-v1",
                as_of=date(2026, 9, 1),
                calculated_at=newer,
                signal_count=1,
                breakdown={},
                fingerprint="m105-inv",
                created_at=newer,
            ),
        ]
    )
    db_session.add(
        AnomalySignalRecord(
            anomaly_type="PRICE_VARIANCE",
            severity="CRITICAL",
            score=Decimal("1"),
            vendor_id=vendor.id,
            title="Price variance",
            explanation="Stored deterministic explanation.",
            evidence={"expected": "10", "observed": "40"},
            fingerprint="m105-signal",
            detected_at=newer,
        )
    )
    db_session.add(
        AnomalyScanJob(
            scan_type="FULL",
            status="COMPLETED",
            requested_at=newer,
            completed_at=newer,
            processed_count=3,
            anomaly_count=1,
            error_count=0,
            created_at=newer,
            updated_at=newer,
        )
    )
    db_session.flush()

    client = _client(db_session)
    try:
        listed = client.get("/risk/profiles")
        assert listed.status_code == 200
        body = listed.json()
        assert body["counts_by_band"]["LOW"] == 1
        assert body["counts_by_band"]["CRITICAL"] == 0
        assert body["counts_by_band"]["MEDIUM"] == 1
        assert body["total"] == 2
        vendor_row = next(item for item in body["items"] if item["entity_type"] == "VENDOR")
        assert vendor_row["score"] == 12
        assert vendor_row["entity_label"] == "Northwind"

        history = client.get(f"/risk/profiles/VENDOR/{vendor.id}")
        assert history.status_code == 200
        current = history.json()["current"]
        assert current["score"] == 12
        assert current["as_of"] == "2026-09-01"
        assert len(history.json()["history"]) == 2
        assert "10" in history.text

        point = client.get(f"/risk/profiles/VENDOR/{vendor.id}", params={"as_of": "2026-01-01"})
        assert point.json()["current"]["score"] == 90
        assert len(point.json()["history"]) == 2

        empty_point = client.get(
            f"/risk/profiles/VENDOR/{vendor.id}", params={"as_of": "2020-01-01"}
        )
        assert empty_point.status_code == 200
        assert empty_point.json()["current"] is None

        signals = client.get("/anomalies", params={"high_or_critical": True, "limit": 10})
        assert signals.status_code == 200
        assert signals.json()["items"][0]["severity"] == "CRITICAL"
        assert signals.json()["items"][0]["explanation"] == "Stored deterministic explanation."

        scans = client.get("/anomalies/scans")
        assert scans.json()["items"][0]["status"] == "COMPLETED"
        assert scans.json()["items"][0]["anomaly_count"] == 1
    finally:
        app.dependency_overrides.clear()
