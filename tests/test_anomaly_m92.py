"""M9.2 — Batch anomaly scanning and analytics."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.anomaly.analytics import (
    get_anomaly_summary,
    get_anomaly_trends,
    get_vendor_anomaly_summary,
)
from app.anomaly.enums import AnomalyScanStatus, AnomalyScanType, AnomalyType
from app.anomaly.pagination import (
    AnomalyCursorError,
    decode_anomaly_cursor,
    encode_anomaly_cursor,
)
from app.anomaly.scanner import (
    AnomalyScanConflictError,
    AnomalyScanError,
    AnomalyScanService,
)
from app.db.models import (
    AnomalyScanJob,
    AnomalySignalRecord,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)
from app.db.session import get_db
from app.domain.enums import InvoiceStatus, PurchaseOrderStatus
from app.main import app
from app.services.anomaly_service import AnomalyService


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


def _vendor(session: Session) -> Vendor:
    v = Vendor(name=f"V-{uuid4().hex[:6]}", tax_id=f"T-{uuid4().hex[:8]}")
    session.add(v)
    session.flush()
    return v


def _po(session: Session, vendor: Vendor, *, price: Decimal = Decimal("100")) -> PurchaseOrder:
    po = PurchaseOrder(
        po_number=f"PO-{uuid4().hex[:8]}",
        vendor_id=vendor.id,
        order_date=date(2026, 1, 1),
        currency="USD",
        status=PurchaseOrderStatus.OPEN.value,
    )
    session.add(po)
    session.flush()
    session.add(
        PurchaseOrderLine(
            purchase_order_id=po.id,
            line_number=1,
            description="Item",
            quantity=Decimal("10"),
            unit_price=price,
            tax_rate=Decimal("0"),
        )
    )
    session.flush()
    session.refresh(po)
    return po


def _invoice(
    session: Session,
    vendor: Vendor,
    po: PurchaseOrder,
    *,
    price: Decimal = Decimal("100"),
    invoice_date: date = date(2026, 1, 15),
) -> Invoice:
    inv = Invoice(
        invoice_number=f"INV-{uuid4().hex[:10]}",
        vendor_id=vendor.id,
        purchase_order_id=po.id,
        invoice_date=invoice_date,
        currency="USD",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=price * Decimal("10"),
        tax_amount=Decimal("0"),
        total_amount=price * Decimal("10"),
    )
    session.add(inv)
    session.flush()
    session.add(
        InvoiceLine(
            invoice_id=inv.id,
            purchase_order_line_id=po.lines[0].id,
            line_number=1,
            description="Item",
            quantity=Decimal("10"),
            unit_price=price,
            tax_rate=Decimal("0"),
        )
    )
    session.flush()
    session.refresh(inv)
    return inv


def _seed_invoices(
    session: Session, n: int, *, price: Decimal = Decimal("150")
) -> list[Invoice]:
    vendor = _vendor(session)
    po = _po(session, vendor, price=Decimal("100"))
    return [_invoice(session, vendor, po, price=price) for _ in range(n)]


# --- Scanner ---


def test_batch_processing_and_checkpoint(db_session: Session) -> None:
    invoices = _seed_invoices(db_session, 5)
    db_session.commit()
    service = AnomalyScanService(db_session, batch_size=2)
    job, _ = service.create_scan(scan_type=AnomalyScanType.INVOICE)
    done = service.run_scan(job.id)
    assert done.status == AnomalyScanStatus.COMPLETED.value
    assert done.processed_count == 5
    assert done.last_cursor == str(sorted(i.id for i in invoices)[-1])
    assert done.anomaly_count >= 1


def test_deterministic_ordering(db_session: Session) -> None:
    _seed_invoices(db_session, 4)
    db_session.commit()
    service = AnomalyScanService(db_session, batch_size=2)
    ids = service._fetch_batch_ids("invoice", after_id=None)
    assert ids == sorted(ids)


def test_failure_resume_matches_full_run(db_session: Session) -> None:
    invoices = _seed_invoices(db_session, 6)
    db_session.commit()

    # Clean baseline: successful full run fingerprints
    baseline = AnomalyScanService(db_session, batch_size=2)
    base_job, _ = baseline.create_scan(scan_type=AnomalyScanType.INVOICE, scan_key="baseline")
    baseline.run_scan(base_job.id)
    baseline_fps = {
        r.fingerprint for r in db_session.scalars(select(AnomalySignalRecord)).all()
    }

    # Wipe signals + jobs for resume experiment (keep invoices)
    for row in db_session.scalars(select(AnomalySignalRecord)).all():
        db_session.delete(row)
    for row in db_session.scalars(select(AnomalyScanJob)).all():
        db_session.delete(row)
    db_session.commit()

    service = AnomalyScanService(db_session, batch_size=2)
    job, _ = service.create_scan(scan_type=AnomalyScanType.INVOICE, scan_key="resume-test")

    call_count = {"n": 0}
    original = service._process_batch

    def flaky_batch(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] == 3:
            raise OperationalError("stmt", {}, Exception("boom"))
        return original(*args, **kwargs)

    service._process_batch = flaky_batch  # type: ignore[method-assign]
    failed = service.run_scan(job.id)
    assert failed.status == AnomalyScanStatus.FAILED.value
    assert failed.processed_count == 4  # two successful batches of 2
    assert failed.last_cursor is not None
    checkpoint = failed.last_cursor

    # Resume without flaky patch
    service2 = AnomalyScanService(db_session, batch_size=2)
    resumed = service2.resume_scan(job.id)
    assert resumed.status == AnomalyScanStatus.COMPLETED.value
    assert resumed.processed_count == 6
    assert resumed.last_cursor == str(sorted(i.id for i in invoices)[-1])
    # Checkpoint advanced beyond failure point
    assert resumed.last_cursor != checkpoint or resumed.processed_count == 6

    final_fps = {
        r.fingerprint for r in db_session.scalars(select(AnomalySignalRecord)).all()
    }
    assert final_fps == baseline_fps


def test_isolated_rule_error_continues(db_session: Session) -> None:
    _seed_invoices(db_session, 3)
    db_session.commit()
    service = AnomalyScanService(db_session, batch_size=10)
    job, _ = service.create_scan(scan_type=AnomalyScanType.INVOICE)
    ids = service._fetch_batch_ids("invoice", after_id=None)
    bad_id = ids[1]
    original = service._detect_entity

    def boom(entity, entity_id):
        if entity_id == bad_id:
            raise RuntimeError("isolated")
        return original(entity, entity_id)

    service._detect_entity = boom  # type: ignore[method-assign]
    done = service.run_scan(job.id)
    assert done.status == AnomalyScanStatus.COMPLETED.value
    assert done.error_count == 1
    assert done.processed_count == 3


def test_cancel_preserves_signals(db_session: Session) -> None:
    _seed_invoices(db_session, 4)
    db_session.commit()
    service = AnomalyScanService(db_session, batch_size=2)
    job, _ = service.create_scan(scan_type=AnomalyScanType.INVOICE)

    # Run one batch manually then cancel
    job.status = AnomalyScanStatus.RUNNING.value
    job.started_at = datetime.now(UTC)
    db_session.flush()
    ids = service._fetch_batch_ids("invoice", after_id=None)
    service._process_batch(job, entity="invoice", ids=ids, phase=None, commit=True)
    before = db_session.scalar(select(func.count()).select_from(AnomalySignalRecord))
    cancelled = service.cancel_scan(job.id)
    assert cancelled.status == AnomalyScanStatus.CANCELLED.value
    after = db_session.scalar(select(func.count()).select_from(AnomalySignalRecord))
    assert after == before
    with pytest.raises(AnomalyScanConflictError):
        service.run_scan(job.id)


def test_scan_key_idempotency(db_session: Session) -> None:
    service = AnomalyScanService(db_session)
    a, reused_a = service.create_scan(
        scan_type=AnomalyScanType.FULL, scan_key="daily-2026-09-22"
    )
    b, reused_b = service.create_scan(
        scan_type=AnomalyScanType.FULL, scan_key="daily-2026-09-22"
    )
    assert reused_a is False
    assert reused_b is True
    assert a.id == b.id


def test_invalid_scan_type() -> None:
    # Pure validation without DB
    with pytest.raises(ValueError):
        AnomalyScanType("EVERYTHING")


def test_invalid_transitions(db_session: Session) -> None:
    service = AnomalyScanService(db_session)
    job, _ = service.create_scan(scan_type=AnomalyScanType.VENDOR)
    service.cancel_scan(job.id)
    with pytest.raises(AnomalyScanConflictError):
        service.cancel_scan(job.id)
    with pytest.raises(AnomalyScanConflictError):
        service.resume_scan(job.id)


# --- Analytics ---


def test_analytics_summary_and_trends(db_session: Session) -> None:
    vendor = _vendor(db_session)
    po = _po(db_session, vendor)
    inv = _invoice(db_session, vendor, po, price=Decimal("150"))
    AnomalyService(db_session).detect_for_invoice(inv.id)
    empty = get_anomaly_summary(db_session, vendor_id=uuid4())
    assert empty["total_signals"] == 0

    summary = get_anomaly_summary(db_session)
    assert summary["total_signals"] >= 1
    assert AnomalyType.PRICE_VARIANCE.value in summary["counts_by_type"]
    assert summary["unique_affected_vendors"] >= 1
    assert summary["unique_affected_invoices"] >= 1
    assert summary["unique_affected_pos"] >= 1
    risk = summary["risk_signal_summary"]
    assert risk["open_signal_count"] == summary["total_signals"]

    vsum = get_vendor_anomaly_summary(db_session, vendor.id)
    assert vsum["profile_kind"] == "anomaly_profile"
    assert vsum["total_anomalies"] >= 1

    daily = get_anomaly_trends(db_session, period="daily")
    assert isinstance(daily, list)
    weekly = get_anomaly_trends(db_session, period="weekly")
    monthly = get_anomaly_trends(db_session, period="monthly")
    assert isinstance(weekly, list)
    assert isinstance(monthly, list)


# --- Pagination ---


def test_cursor_pagination_stable(db_session: Session) -> None:
    vendor = _vendor(db_session)
    po = _po(db_session, vendor)
    for _ in range(5):
        inv = _invoice(db_session, vendor, po, price=Decimal("150"))
        AnomalyService(db_session).detect_for_invoice(inv.id)

    service = AnomalyService(db_session)
    page1, cursor1 = service.list_anomalies_page(limit=2)
    assert len(page1) == 2
    assert cursor1
    page2, cursor2 = service.list_anomalies_page(limit=2, cursor=cursor1)
    assert len(page2) == 2
    ids1 = {r.id for r in page1}
    ids2 = {r.id for r in page2}
    assert ids1.isdisjoint(ids2)
    # Ordering stable
    assert (page1[0].detected_at, page1[0].id) >= (page1[1].detected_at, page1[1].id)

    with pytest.raises(AnomalyCursorError):
        decode_anomaly_cursor("not-a-cursor")
    enc = encode_anomaly_cursor(detected_at=page1[0].detected_at, anomaly_id=page1[0].id)
    ts, aid = decode_anomaly_cursor(enc)
    assert aid == page1[0].id
    assert ts == page1[0].detected_at


# --- API ---


def test_api_scan_lifecycle(api_client: TestClient, db_session: Session) -> None:
    _seed_invoices(db_session, 3)
    db_session.commit()
    created = api_client.post(
        "/anomalies/scans",
        json={"scan_type": "INVOICE", "scan_key": "api-scan-1"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "PENDING"
    scan_id = body["scan_id"]

    reused = api_client.post(
        "/anomalies/scans",
        json={"scan_type": "INVOICE", "scan_key": "api-scan-1"},
    )
    assert reused.json()["reused_existing"] is True
    assert reused.json()["scan_id"] == scan_id

    bad = api_client.post("/anomalies/scans", json={"scan_type": "EVERYTHING"})
    assert bad.status_code == 422

    ran = api_client.post(f"/anomalies/scans/{scan_id}/run")
    assert ran.status_code == 200
    assert ran.json()["status"] == "COMPLETED"
    assert ran.json()["processed_count"] == 3

    got = api_client.get(f"/anomalies/scans/{scan_id}")
    assert got.status_code == 200
    assert got.json()["anomaly_count"] >= 0


def test_api_cancel(api_client: TestClient, db_session: Session) -> None:
    job = AnomalyScanJob(
        scan_type=AnomalyScanType.INVOICE.value,
        status=AnomalyScanStatus.PENDING.value,
        requested_at=datetime.now(UTC),
    )
    db_session.add(job)
    db_session.commit()
    resp = api_client.post(f"/anomalies/scans/{job.id}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"


def test_api_analytics_and_pagination(api_client: TestClient, db_session: Session) -> None:
    vendor = _vendor(db_session)
    po = _po(db_session, vendor)
    for _ in range(3):
        inv = _invoice(db_session, vendor, po, price=Decimal("150"))
        AnomalyService(db_session).detect_for_invoice(inv.id)
    db_session.commit()

    summary = api_client.get("/anomalies/summary")
    assert summary.status_code == 200
    assert summary.json()["total_signals"] >= 1

    vsum = api_client.get(f"/anomalies/vendors/{vendor.id}/summary")
    assert vsum.status_code == 200
    assert vsum.json()["profile_kind"] == "anomaly_profile"

    trends = api_client.get("/anomalies/trends", params={"period": "daily"})
    assert trends.status_code == 200
    assert "points" in trends.json()

    page = api_client.get("/anomalies", params={"limit": 2})
    assert page.status_code == 200
    data = page.json()
    assert len(data["items"]) == 2
    assert data["next_cursor"]
    page2 = api_client.get(
        "/anomalies", params={"limit": 2, "cursor": data["next_cursor"]}
    )
    assert page2.status_code == 200
    bad_cursor = api_client.get("/anomalies", params={"cursor": "!!!"})
    assert bad_cursor.status_code == 422


def test_no_procurement_mutation_during_scan(db_session: Session) -> None:
    invoices = _seed_invoices(db_session, 2)
    db_session.commit()
    before = [(i.id, i.total_amount, i.lines[0].unit_price) for i in invoices]
    service = AnomalyScanService(db_session, batch_size=10)
    job, _ = service.create_scan(scan_type=AnomalyScanType.INVOICE)
    service.run_scan(job.id)
    for inv_id, total, price in before:
        inv = db_session.get(Invoice, inv_id)
        assert inv is not None
        db_session.refresh(inv)
        assert inv.total_amount == total
        assert inv.lines[0].unit_price == price


def test_create_scan_error_message() -> None:
    # Ensure AnomalyScanError message for bad type via service without session ops
    from unittest.mock import MagicMock

    svc = AnomalyScanService(MagicMock(), batch_size=1)
    with pytest.raises(AnomalyScanError):
        svc.create_scan(scan_type="NOPE")
