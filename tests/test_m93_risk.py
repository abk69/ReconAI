"""M9.3 — Transparent deterministic risk scoring."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.anomaly.enums import AnomalySeverity, AnomalyType
from app.db.models import (
    AnomalySignalRecord,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    RiskProfileRecord,
    Vendor,
)
from app.db.session import get_db
from app.domain.enums import InvoiceStatus, PurchaseOrderStatus
from app.main import app
from app.risk.contracts import RiskScoringConfig
from app.risk.enums import RISK_SCORE_VERSION, RiskBand, RiskEntityType
from app.risk.fingerprints import build_risk_fingerprint
from app.risk.profiles import build_profile
from app.risk.scoring import (
    band_for_score,
    calculate_score,
    normalize_score,
    recency_multiplier,
)
from app.services.risk_service import RiskService


@dataclass
class FakeSignal:
    id: UUID
    anomaly_type: str
    severity: str
    fingerprint: str
    detected_at: datetime


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


def _sig(
    *,
    atype: AnomalyType = AnomalyType.PRICE_VARIANCE,
    severity: AnomalySeverity = AnomalySeverity.HIGH,
    days_ago: int = 0,
    as_of: date = date(2026, 6, 1),
    fingerprint: str | None = None,
) -> FakeSignal:
    detected = datetime.combine(as_of - timedelta(days=days_ago), datetime.min.time()).replace(
        tzinfo=UTC
    )
    return FakeSignal(
        id=uuid4(),
        anomaly_type=atype.value,
        severity=severity.value,
        fingerprint=fingerprint or f"fp-{uuid4().hex}",
        detected_at=detected,
    )


# --- Formula ---


def test_single_signal_formula() -> None:
    cfg = RiskScoringConfig()
    as_of = date(2026, 6, 1)
    # PRICE_VARIANCE HIGH recent: 15 * 0.75 * 1.0 = 11.25
    # aggregate 11.25 / 180 * 100 = 6.25 → 6
    sig = _sig(as_of=as_of)
    score, band, contribs, breakdown, _ = calculate_score([sig], as_of=as_of, config=cfg)
    assert contribs[0].raw_contribution == Decimal("11.2500")
    assert breakdown[0].contribution == Decimal("11.2500")
    assert score == normalize_score(Decimal("11.25"), cfg)
    assert score == 6
    assert band == RiskBand.LOW


def test_severity_multipliers() -> None:
    cfg = RiskScoringConfig()
    as_of = date(2026, 6, 1)
    for sev, mult in [
        (AnomalySeverity.LOW, Decimal("0.25")),
        (AnomalySeverity.MEDIUM, Decimal("0.50")),
        (AnomalySeverity.HIGH, Decimal("0.75")),
        (AnomalySeverity.CRITICAL, Decimal("1.00")),
    ]:
        sig = _sig(severity=sev, as_of=as_of)
        _, _, contribs, _, _ = calculate_score([sig], as_of=as_of, config=cfg)
        assert contribs[0].severity_multiplier == mult
        assert contribs[0].raw_contribution == (
            Decimal("15") * mult * Decimal("1")
        ).quantize(Decimal("0.0001"))


def test_recency_buckets() -> None:
    cfg = RiskScoringConfig()
    assert recency_multiplier(0, cfg) == Decimal("1.00")
    assert recency_multiplier(30, cfg) == Decimal("1.00")
    assert recency_multiplier(31, cfg) == Decimal("0.75")
    assert recency_multiplier(90, cfg) == Decimal("0.75")
    assert recency_multiplier(91, cfg) == Decimal("0.50")
    assert recency_multiplier(180, cfg) == Decimal("0.50")
    assert recency_multiplier(181, cfg) == Decimal("0.25")


def test_type_cap_prevents_domination() -> None:
    cfg = RiskScoringConfig()
    as_of = date(2026, 6, 1)
    # Many CRITICAL TIMING anomalies: weight 10 * 1.0 = 10 each, cap 20
    signals = [
        _sig(
            atype=AnomalyType.TIMING_ANOMALY,
            severity=AnomalySeverity.CRITICAL,
            as_of=as_of,
            fingerprint=f"t-{i}",
        )
        for i in range(10)
    ]
    score, _, contribs, breakdown, _ = calculate_score(signals, as_of=as_of, config=cfg)
    assert len(contribs) == 10
    assert breakdown[0].uncapped_contribution == Decimal("100.0000")
    assert breakdown[0].contribution == Decimal("20.0000")  # capped
    assert score == normalize_score(Decimal("20"), cfg)


def test_zero_and_hundred_cap() -> None:
    cfg = RiskScoringConfig()
    as_of = date(2026, 6, 1)
    score0, band0, _, _, _ = calculate_score([], as_of=as_of, config=cfg)
    assert score0 == 0
    assert band0 == RiskBand.LOW

    # Push every type to its cap with CRITICAL recent signals
    signals: list[FakeSignal] = []
    for atype in AnomalyType:
        # Enough CRITICAL signals to hit each cap
        for i in range(10):
            signals.append(
                _sig(
                    atype=atype,
                    severity=AnomalySeverity.CRITICAL,
                    as_of=as_of,
                    fingerprint=f"{atype.value}-{i}",
                )
            )
    score, band, _, breakdown, _ = calculate_score(signals, as_of=as_of, config=cfg)
    assert sum(b.contribution for b in breakdown) == cfg.max_aggregate()
    assert score == 100
    assert band == RiskBand.CRITICAL


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0, RiskBand.LOW),
        (24, RiskBand.LOW),
        (25, RiskBand.MEDIUM),
        (49, RiskBand.MEDIUM),
        (50, RiskBand.HIGH),
        (74, RiskBand.HIGH),
        (75, RiskBand.CRITICAL),
        (100, RiskBand.CRITICAL),
    ],
)
def test_band_boundaries(score: int, expected: RiskBand) -> None:
    assert band_for_score(score, RiskScoringConfig()) == expected


# --- Fingerprint ---


def test_fingerprint_deterministic() -> None:
    as_of = date(2026, 6, 1)
    fps = ["b", "a"]
    a = build_risk_fingerprint(
        entity_type="VENDOR",
        entity_id="v1",
        score_version=RISK_SCORE_VERSION,
        as_of=as_of,
        signal_fingerprints=fps,
    )
    b = build_risk_fingerprint(
        entity_type="VENDOR",
        entity_id="v1",
        score_version=RISK_SCORE_VERSION,
        as_of=as_of,
        signal_fingerprints=["a", "b"],
    )
    assert a == b
    c = build_risk_fingerprint(
        entity_type="VENDOR",
        entity_id="v1",
        score_version=RISK_SCORE_VERSION,
        as_of=date(2026, 6, 2),
        signal_fingerprints=fps,
    )
    assert a != c
    d = build_risk_fingerprint(
        entity_type="VENDOR",
        entity_id="v1",
        score_version=RISK_SCORE_VERSION,
        as_of=as_of,
        signal_fingerprints=["a", "b", "c"],
    )
    assert a != d


# --- Persistence / entities ---


def _seed_vendor_po_invoice(session: Session) -> tuple[Vendor, PurchaseOrder, Invoice]:
    vendor = Vendor(name="RiskCo", tax_id=f"T-{uuid4().hex[:8]}")
    session.add(vendor)
    session.flush()
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
            description="x",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            tax_rate=Decimal("0"),
        )
    )
    session.flush()
    inv = Invoice(
        invoice_number=f"INV-{uuid4().hex[:8]}",
        vendor_id=vendor.id,
        purchase_order_id=po.id,
        invoice_date=date(2026, 1, 15),
        currency="USD",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=Decimal("100"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("100"),
    )
    session.add(inv)
    session.flush()
    session.add(
        InvoiceLine(
            invoice_id=inv.id,
            purchase_order_line_id=po.lines[0].id,
            line_number=1,
            description="x",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            tax_rate=Decimal("0"),
        )
    )
    session.flush()
    return vendor, po, inv


def _add_signal(
    session: Session,
    *,
    vendor_id: UUID | None = None,
    invoice_id: UUID | None = None,
    po_id: UUID | None = None,
    atype: AnomalyType = AnomalyType.PRICE_VARIANCE,
    severity: AnomalySeverity = AnomalySeverity.CRITICAL,
    detected_at: datetime | None = None,
) -> AnomalySignalRecord:
    row = AnomalySignalRecord(
        anomaly_type=atype.value,
        severity=severity.value,
        score=Decimal("1"),
        vendor_id=vendor_id,
        invoice_id=invoice_id,
        purchase_order_id=po_id,
        title="t",
        explanation="e",
        evidence={"k": "v"},
        fingerprint=f"fp-{uuid4().hex}",
        detected_at=detected_at or datetime(2026, 5, 1, tzinfo=UTC),
    )
    session.add(row)
    session.flush()
    return row


def test_entity_scoping_excludes_unrelated(db_session: Session) -> None:
    v1, po1, inv1 = _seed_vendor_po_invoice(db_session)
    v2, po2, inv2 = _seed_vendor_po_invoice(db_session)
    _add_signal(db_session, vendor_id=v1.id, invoice_id=inv1.id, po_id=po1.id)
    _add_signal(
        db_session,
        vendor_id=v2.id,
        invoice_id=inv2.id,
        po_id=po2.id,
        atype=AnomalyType.DUPLICATE_INVOICE,
    )
    db_session.commit()
    service = RiskService(db_session)
    as_of = date(2026, 6, 1)
    vendor_row = service.calculate_vendor_risk(v1.id, as_of=as_of)
    inv_row = service.calculate_invoice_risk(inv1.id, as_of=as_of)
    po_row = service.calculate_po_risk(po1.id, as_of=as_of)
    assert vendor_row.signal_count == 1
    assert inv_row.signal_count == 1
    assert po_row.signal_count == 1
    # v2 signal not on v1
    assert vendor_row.score == inv_row.score


def test_immutability_and_fingerprint_reuse(db_session: Session) -> None:
    vendor, po, inv = _seed_vendor_po_invoice(db_session)
    _add_signal(db_session, vendor_id=vendor.id, invoice_id=inv.id, po_id=po.id)
    db_session.commit()
    service = RiskService(db_session)
    as_of = date(2026, 6, 1)
    a = service.calculate_vendor_risk(vendor.id, as_of=as_of)
    b = service.calculate_vendor_risk(vendor.id, as_of=as_of)
    assert a.id == b.id
    count = db_session.scalar(select(func.count()).select_from(RiskProfileRecord))
    assert count == 1
    # Different as_of → new row
    c = service.calculate_vendor_risk(vendor.id, as_of=date(2026, 7, 1))
    assert c.id != a.id
    assert c.as_of == date(2026, 7, 1)
    # Historical a unchanged
    db_session.refresh(a)
    assert a.score == b.score


def test_version_creates_distinct_profile(db_session: Session) -> None:
    vendor, po, inv = _seed_vendor_po_invoice(db_session)
    _add_signal(db_session, vendor_id=vendor.id, invoice_id=inv.id, po_id=po.id)
    db_session.commit()
    as_of = date(2026, 6, 1)
    s1 = RiskService(db_session, config=RiskScoringConfig(score_version="m9.3-v1"))
    r1 = s1.calculate_vendor_risk(vendor.id, as_of=as_of)
    s2 = RiskService(db_session, config=RiskScoringConfig(score_version="m9.3-v2"))
    r2 = s2.calculate_vendor_risk(vendor.id, as_of=as_of)
    assert r1.id != r2.id
    assert r1.score_version == "m9.3-v1"
    assert r2.score_version == "m9.3-v2"


def test_profile_breakdown_structure() -> None:
    as_of = date(2026, 6, 1)
    sigs = [
        _sig(atype=AnomalyType.VENDOR_SPIKE, severity=AnomalySeverity.HIGH, as_of=as_of),
        _sig(
            atype=AnomalyType.REPEATED_MISMATCH,
            severity=AnomalySeverity.MEDIUM,
            as_of=as_of,
        ),
    ]
    profile = build_profile(
        entity_type=RiskEntityType.VENDOR,
        entity_id=uuid4(),
        signals=sigs,
        as_of=as_of,
    )
    assert profile.signal_count == 2
    types = {b.anomaly_type for b in profile.breakdown}
    assert AnomalyType.VENDOR_SPIKE in types
    notes = profile.formula_notes.casefold()
    assert "not" in notes and "fraud" in notes


def test_no_financial_mutation(db_session: Session) -> None:
    vendor, po, inv = _seed_vendor_po_invoice(db_session)
    _add_signal(db_session, vendor_id=vendor.id, invoice_id=inv.id, po_id=po.id)
    db_session.commit()
    before = inv.total_amount
    RiskService(db_session).calculate_invoice_risk(inv.id, as_of=date(2026, 6, 1))
    db_session.refresh(inv)
    assert inv.total_amount == before


# --- API ---


def test_api_risk_endpoints(api_client: TestClient, db_session: Session) -> None:
    vendor, po, inv = _seed_vendor_po_invoice(db_session)
    _add_signal(
        db_session,
        vendor_id=vendor.id,
        invoice_id=inv.id,
        po_id=po.id,
        severity=AnomalySeverity.CRITICAL,
    )
    db_session.commit()

    v = api_client.get(f"/risk/vendors/{vendor.id}", params={"as_of": "2026-06-01"})
    assert v.status_code == 200
    body = v.json()
    assert body["entity_type"] == "VENDOR"
    assert 0 <= body["score"] <= 100
    assert body["score_version"] == RISK_SCORE_VERSION
    assert "not a probability of fraud" in body["note"].casefold()
    assert "chance of fraud" not in body["note"].casefold()

    i = api_client.get(f"/risk/invoices/{inv.id}", params={"as_of": "2026-06-01"})
    assert i.status_code == 200
    p = api_client.get(
        f"/risk/purchase-orders/{po.id}", params={"as_of": "2026-06-01"}
    )
    assert p.status_code == 200
    assert api_client.get(f"/risk/vendors/{uuid4()}").status_code == 404
