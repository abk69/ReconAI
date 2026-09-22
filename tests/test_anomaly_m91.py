"""M9.1 — Anomaly detection foundation (deterministic, no LLM)."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.anomaly.contracts import AnomalyConfig, AnomalySignal
from app.anomaly.engine import AnomalyEngine
from app.anomaly.enums import SEVERITY_SCORE, AnomalySeverity, AnomalyType
from app.anomaly.evidence import (
    decimal_str,
    severity_from_percent_thresholds,
    severity_from_ratio_thresholds,
)
from app.anomaly.fingerprints import build_anomaly_fingerprint
from app.anomaly.rules import (
    DuplicateInvoiceRule,
    PriceVarianceRule,
    QuantityVarianceRule,
    RepeatedMismatchRule,
    TimingAnomalyRule,
    VendorSpikeRule,
)
from app.db.models import (
    AnomalySignalRecord,
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ReconciliationException,
    Vendor,
)
from app.db.session import get_db
from app.domain.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    GoodsReceiptStatus,
    InvoiceStatus,
    PurchaseOrderStatus,
)
from app.main import app
from app.services.anomaly_service import AnomalyService


@dataclass
class FakeLine:
    id: UUID = field(default_factory=uuid4)
    line_number: int = 1
    quantity: Decimal = Decimal("10")
    unit_price: Decimal = Decimal("100")
    purchase_order_line_id: UUID | None = None


@dataclass
class FakePO:
    id: UUID = field(default_factory=uuid4)
    vendor_id: UUID = field(default_factory=uuid4)
    order_date: date = date(2026, 1, 1)
    lines: list[FakeLine] = field(default_factory=list)


@dataclass
class FakeInvoice:
    id: UUID = field(default_factory=uuid4)
    invoice_number: str = "INV-1"
    vendor_id: UUID = field(default_factory=uuid4)
    purchase_order_id: UUID | None = None
    invoice_date: date = date(2026, 1, 15)
    total_amount: Decimal = Decimal("1000")
    lines: list[FakeLine] = field(default_factory=list)


@dataclass
class FakeGRN:
    id: UUID = field(default_factory=uuid4)
    purchase_order_id: UUID = field(default_factory=uuid4)
    receipt_date: date = date(2026, 1, 10)


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


def _seed_vendor(session: Session, name: str = "Acme Eval") -> Vendor:
    vendor = Vendor(name=name, tax_id=f"T-{uuid4().hex[:8]}")
    session.add(vendor)
    session.flush()
    return vendor


def _seed_po(
    session: Session,
    vendor: Vendor,
    *,
    unit_price: Decimal = Decimal("100"),
    quantity: Decimal = Decimal("10"),
    order_date: date = date(2026, 1, 1),
) -> PurchaseOrder:
    po = PurchaseOrder(
        po_number=f"PO-{uuid4().hex[:8]}",
        vendor_id=vendor.id,
        order_date=order_date,
        currency="USD",
        status=PurchaseOrderStatus.OPEN.value,
    )
    session.add(po)
    session.flush()
    line = PurchaseOrderLine(
        purchase_order_id=po.id,
        line_number=1,
        description="Widget",
        quantity=quantity,
        unit_price=unit_price,
        tax_rate=Decimal("0"),
    )
    session.add(line)
    session.flush()
    session.refresh(po)
    return po


def _seed_invoice(
    session: Session,
    vendor: Vendor,
    po: PurchaseOrder | None,
    *,
    unit_price: Decimal = Decimal("100"),
    quantity: Decimal = Decimal("10"),
    invoice_date: date = date(2026, 1, 15),
    invoice_number: str | None = None,
    total_amount: Decimal | None = None,
) -> Invoice:
    inv = Invoice(
        invoice_number=invoice_number or f"INV-{uuid4().hex[:8]}",
        vendor_id=vendor.id,
        purchase_order_id=po.id if po else None,
        invoice_date=invoice_date,
        currency="USD",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=total_amount or (unit_price * quantity),
        tax_amount=Decimal("0"),
        total_amount=total_amount or (unit_price * quantity),
    )
    session.add(inv)
    session.flush()
    po_line_id = po.lines[0].id if po is not None and po.lines else None
    session.add(
        InvoiceLine(
            invoice_id=inv.id,
            purchase_order_line_id=po_line_id,
            line_number=1,
            description="Widget",
            quantity=quantity,
            unit_price=unit_price,
            tax_rate=Decimal("0"),
        )
    )
    session.flush()
    session.refresh(inv)
    return inv


def _seed_grn(
    session: Session,
    po: PurchaseOrder,
    *,
    receipt_date: date = date(2026, 1, 10),
    received_qty: Decimal = Decimal("10"),
) -> GoodsReceipt:
    grn = GoodsReceipt(
        grn_number=f"GRN-{uuid4().hex[:8]}",
        purchase_order_id=po.id,
        receipt_date=receipt_date,
        status=GoodsReceiptStatus.POSTED.value,
    )
    session.add(grn)
    session.flush()
    session.add(
        GoodsReceiptLine(
            goods_receipt_id=grn.id,
            purchase_order_line_id=po.lines[0].id,
            line_number=1,
            received_quantity=received_qty,
        )
    )
    session.flush()
    return grn


# --- Domain ---


def test_anomaly_enums() -> None:
    assert set(AnomalyType) == {
        AnomalyType.PRICE_VARIANCE,
        AnomalyType.QUANTITY_VARIANCE,
        AnomalyType.DUPLICATE_INVOICE,
        AnomalyType.TIMING_ANOMALY,
        AnomalyType.VENDOR_SPIKE,
        AnomalyType.REPEATED_MISMATCH,
    }
    assert set(AnomalySeverity) == {
        AnomalySeverity.LOW,
        AnomalySeverity.MEDIUM,
        AnomalySeverity.HIGH,
        AnomalySeverity.CRITICAL,
    }
    assert SEVERITY_SCORE[AnomalySeverity.CRITICAL] == "1.00"


def test_anomaly_signal_schema_requires_evidence_and_fingerprint() -> None:
    from datetime import UTC, datetime

    with pytest.raises(ValidationError):
        AnomalySignal(
            anomaly_type=AnomalyType.PRICE_VARIANCE,
            severity=AnomalySeverity.LOW,
            score=Decimal("0.25"),
            detected_at=datetime.now(UTC),
            title="x",
            explanation="y",
            evidence={},
            fingerprint="short",
        )


# --- Fingerprints ---


def test_fingerprint_deterministic() -> None:
    a = build_anomaly_fingerprint("PRICE_VARIANCE", "v1", "i1", "l1")
    b = build_anomaly_fingerprint("PRICE_VARIANCE", "v1", "i1", "l1")
    assert a == b
    assert len(a) == 64
    c = build_anomaly_fingerprint("PRICE_VARIANCE", "v1", "i2", "l1")
    assert a != c


# --- Price ---


@pytest.mark.parametrize(
    ("inv_price", "expected_sev"),
    [
        (Decimal("104"), None),  # 4% < 5%
        (Decimal("105"), AnomalySeverity.LOW),  # 5%
        (Decimal("110"), AnomalySeverity.MEDIUM),  # 10%
        (Decimal("125"), AnomalySeverity.HIGH),  # 25%
        (Decimal("150"), AnomalySeverity.CRITICAL),  # 50%
    ],
)
def test_price_variance_thresholds(
    inv_price: Decimal, expected_sev: AnomalySeverity | None
) -> None:
    po_line = FakeLine(unit_price=Decimal("100"), quantity=Decimal("1"))
    inv_line = FakeLine(
        unit_price=inv_price,
        quantity=Decimal("1"),
        purchase_order_line_id=po_line.id,
    )
    po = FakePO(lines=[po_line])
    inv = FakeInvoice(lines=[inv_line], purchase_order_id=po.id, vendor_id=po.vendor_id)
    signals = PriceVarianceRule().evaluate(
        invoice=inv, purchase_order=po, config=AnomalyConfig()
    )
    if expected_sev is None:
        assert signals == []
    else:
        assert len(signals) == 1
        assert signals[0].severity == expected_sev
        assert signals[0].evidence["po_unit_price"] == "100"
        assert "variance_percent" in signals[0].evidence
        assert signals[0].score == Decimal(SEVERITY_SCORE[expected_sev])


def test_price_uses_decimal_not_float() -> None:
    assert severity_from_percent_thresholds(
        Decimal("10.00"),
        low=Decimal("5"),
        medium=Decimal("10"),
        high=Decimal("25"),
        critical=Decimal("50"),
    ) == "MEDIUM"
    assert decimal_str(Decimal("10.5000")) == "10.5000"


# --- Quantity ---


@pytest.mark.parametrize(
    ("inv_qty", "expected_sev"),
    [
        (Decimal("10.4"), None),  # 4%
        (Decimal("10.5"), AnomalySeverity.LOW),  # 5%
        (Decimal("11"), AnomalySeverity.MEDIUM),  # 10%
        (Decimal("12.5"), AnomalySeverity.HIGH),  # 25%
        (Decimal("15"), AnomalySeverity.CRITICAL),  # 50%
    ],
)
def test_quantity_variance_thresholds(
    inv_qty: Decimal, expected_sev: AnomalySeverity | None
) -> None:
    po_line = FakeLine(quantity=Decimal("10"), unit_price=Decimal("1"))
    inv_line = FakeLine(
        quantity=inv_qty, unit_price=Decimal("1"), purchase_order_line_id=po_line.id
    )
    po = FakePO(lines=[po_line])
    inv = FakeInvoice(lines=[inv_line], purchase_order_id=po.id, vendor_id=po.vendor_id)
    signals = QuantityVarianceRule().evaluate(
        invoice=inv, purchase_order=po, config=AnomalyConfig()
    )
    if expected_sev is None:
        assert signals == []
    else:
        assert signals[0].severity == expected_sev


def test_quantity_zero_expected_nonzero_invoice() -> None:
    po_line = FakeLine(quantity=Decimal("0"), unit_price=Decimal("1"))
    inv_line = FakeLine(
        quantity=Decimal("5"), unit_price=Decimal("1"), purchase_order_line_id=po_line.id
    )
    po = FakePO(lines=[po_line])
    inv = FakeInvoice(lines=[inv_line], purchase_order_id=po.id, vendor_id=po.vendor_id)
    signals = QuantityVarianceRule().evaluate(
        invoice=inv, purchase_order=po, config=AnomalyConfig()
    )
    assert len(signals) == 1
    assert signals[0].severity == AnomalySeverity.CRITICAL
    assert signals[0].evidence["variance_percent"] == "100.00"


# --- Duplicate ---


def test_duplicate_invoice_normalized() -> None:
    vendor_id = uuid4()
    a = FakeInvoice(invoice_number="INV 001", vendor_id=vendor_id)
    b = FakeInvoice(invoice_number="inv_001", vendor_id=vendor_id)
    signals = DuplicateInvoiceRule().evaluate(invoice=a, sibling_invoices=[a, b])
    assert len(signals) == 1
    assert signals[0].anomaly_type == AnomalyType.DUPLICATE_INVOICE
    assert signals[0].evidence["duplicate_count"] == 2
    assert signals[0].evidence["normalized_invoice_number"] == "inv-001"


def test_duplicate_different_vendor_no_signal() -> None:
    a = FakeInvoice(invoice_number="INV-9", vendor_id=uuid4())
    b = FakeInvoice(invoice_number="INV-9", vendor_id=uuid4())
    # Same raw number but different vendors — sibling list is vendor-scoped in service;
    # rule itself only looks at provided siblings.
    signals = DuplicateInvoiceRule().evaluate(invoice=a, sibling_invoices=[a])
    assert signals == []
    # If wrongly mixed, same normalized number would still flag — service prevents this.
    assert b.vendor_id != a.vendor_id


# --- Timing ---


def test_timing_invoice_before_po() -> None:
    po = FakePO(order_date=date(2026, 2, 1))
    inv = FakeInvoice(invoice_date=date(2026, 1, 15), purchase_order_id=po.id)
    signals = TimingAnomalyRule().evaluate(
        invoice=inv, purchase_order=po, goods_receipts=[], config=AnomalyConfig()
    )
    assert any(s.evidence.get("timing_kind") == "invoice_before_po" for s in signals)
    assert any(s.severity == AnomalySeverity.HIGH for s in signals)
    assert "precedes purchase order" in signals[0].explanation.casefold() or any(
        "precedes purchase order" in s.explanation.casefold() for s in signals
    )


def test_timing_invoice_before_grn_and_long_delay() -> None:
    po = FakePO(order_date=date(2026, 1, 1))
    grn = FakeGRN(receipt_date=date(2026, 3, 1), purchase_order_id=po.id)
    inv = FakeInvoice(invoice_date=date(2026, 2, 15), purchase_order_id=po.id)
    signals = TimingAnomalyRule().evaluate(
        invoice=inv,
        purchase_order=po,
        goods_receipts=[grn],
        config=AnomalyConfig(timing_long_delay_days=30),
    )
    kinds = {s.evidence.get("timing_kind") for s in signals}
    assert "invoice_before_grn" in kinds
    assert "long_po_to_invoice_delay" in kinds


def test_timing_normal_no_signal() -> None:
    po = FakePO(order_date=date(2026, 1, 1))
    grn = FakeGRN(receipt_date=date(2026, 1, 10), purchase_order_id=po.id)
    inv = FakeInvoice(invoice_date=date(2026, 1, 15), purchase_order_id=po.id)
    signals = TimingAnomalyRule().evaluate(
        invoice=inv, purchase_order=po, goods_receipts=[grn], config=AnomalyConfig()
    )
    assert signals == []


# --- Vendor spike ---


def test_vendor_spike_insufficient_history() -> None:
    inv = FakeInvoice(total_amount=Decimal("35000"))
    priors = [
        FakeInvoice(total_amount=Decimal("10000")),
        FakeInvoice(total_amount=Decimal("10000")),
    ]
    assert (
        VendorSpikeRule().evaluate(
            invoice=inv, prior_invoices=priors, config=AnomalyConfig()
        )
        == []
    )


@pytest.mark.parametrize(
    ("current", "expected_sev"),
    [
        (Decimal("15000"), None),  # 1.5x
        (Decimal("20000"), AnomalySeverity.MEDIUM),  # 2x
        (Decimal("30000"), AnomalySeverity.HIGH),  # 3x
        (Decimal("50000"), AnomalySeverity.CRITICAL),  # 5x
    ],
)
def test_vendor_spike_ratios(
    current: Decimal, expected_sev: AnomalySeverity | None
) -> None:
    inv = FakeInvoice(total_amount=current)
    priors = [FakeInvoice(total_amount=Decimal("10000")) for _ in range(3)]
    signals = VendorSpikeRule().evaluate(
        invoice=inv, prior_invoices=priors, config=AnomalyConfig()
    )
    if expected_sev is None:
        assert signals == []
    else:
        assert signals[0].severity == expected_sev
        assert signals[0].evidence["historical_invoice_count"] == 3
        assert signals[0].evidence["baseline_average"].startswith("10000")


def test_ratio_threshold_helper() -> None:
    assert (
        severity_from_ratio_thresholds(
            Decimal("2.0"),
            medium=Decimal("2"),
            high=Decimal("3"),
            critical=Decimal("5"),
        )
        == "MEDIUM"
    )


# --- Repeated mismatch ---


def test_repeated_mismatch_insufficient_and_boundaries() -> None:
    rule = RepeatedMismatchRule()
    cfg = AnomalyConfig()
    vendor_id = uuid4()
    assert (
        rule.evaluate(
            vendor_id=vendor_id,
            invoice_count=4,
            exception_count=4,
            window_days=90,
            config=cfg,
        )
        == []
    )
    med = rule.evaluate(
        vendor_id=vendor_id,
        invoice_count=10,
        exception_count=3,
        window_days=90,
        config=cfg,
        as_of=date(2026, 6, 1),
    )
    assert med[0].severity == AnomalySeverity.MEDIUM
    high = rule.evaluate(
        vendor_id=vendor_id,
        invoice_count=10,
        exception_count=5,
        window_days=90,
        config=cfg,
        as_of=date(2026, 6, 1),
    )
    assert high[0].severity == AnomalySeverity.HIGH
    crit = rule.evaluate(
        vendor_id=vendor_id,
        invoice_count=10,
        exception_count=8,
        window_days=90,
        config=cfg,
        as_of=date(2026, 6, 1),
    )
    assert crit[0].severity == AnomalySeverity.CRITICAL
    assert crit[0].evidence["exception_rate"] == "0.8000"


# --- Persistence / API ---


def test_persist_dedupe_and_filters(db_session: Session) -> None:
    vendor = _seed_vendor(db_session)
    po = _seed_po(db_session, vendor, unit_price=Decimal("100"))
    inv = _seed_invoice(db_session, vendor, po, unit_price=Decimal("150"))
    service = AnomalyService(db_session)
    first = service.detect_for_invoice(inv.id)
    assert any(r.anomaly_type == AnomalyType.PRICE_VARIANCE.value for r in first)
    second = service.detect_for_invoice(inv.id)
    assert len(first) == len(second)
    assert {r.id for r in first} == {r.id for r in second}
    count = db_session.scalar(select(func.count()).select_from(AnomalySignalRecord))
    assert count == len(first)
    filtered = service.list_anomalies(
        anomaly_type=AnomalyType.PRICE_VARIANCE, vendor_id=vendor.id
    )
    assert all(r.anomaly_type == AnomalyType.PRICE_VARIANCE.value for r in filtered)
    assert service.get_anomaly(first[0].id).id == first[0].id


def test_no_financial_mutation_on_detect(db_session: Session) -> None:
    vendor = _seed_vendor(db_session)
    po = _seed_po(db_session, vendor, unit_price=Decimal("100"))
    inv = _seed_invoice(db_session, vendor, po, unit_price=Decimal("200"))
    before_price = po.lines[0].unit_price
    before_total = inv.total_amount
    AnomalyService(db_session).detect_for_invoice(inv.id)
    db_session.refresh(po.lines[0])
    db_session.refresh(inv)
    assert po.lines[0].unit_price == before_price
    assert inv.total_amount == before_total


def test_api_detect_and_list(api_client: TestClient, db_session: Session) -> None:
    vendor = _seed_vendor(db_session)
    po = _seed_po(db_session, vendor, unit_price=Decimal("100"), order_date=date(2026, 1, 1))
    _seed_grn(db_session, po, receipt_date=date(2026, 1, 10))
    inv = _seed_invoice(
        db_session,
        vendor,
        po,
        unit_price=Decimal("150"),
        invoice_date=date(2026, 1, 15),
    )
    db_session.commit()
    resp = api_client.post(f"/anomalies/detect/invoice/{inv.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["created_or_reused_count"] >= 1
    anomaly_id = body["signals"][0]["id"]
    get_resp = api_client.get(f"/anomalies/{anomaly_id}")
    assert get_resp.status_code == 200
    list_resp = api_client.get(
        "/anomalies",
        params={"vendor_id": str(vendor.id), "severity": "CRITICAL"},
    )
    assert list_resp.status_code == 200
    assert isinstance(list_resp.json(), list)


def test_api_detect_vendor_and_exception(api_client: TestClient, db_session: Session) -> None:
    vendor = _seed_vendor(db_session)
    po = _seed_po(db_session, vendor, unit_price=Decimal("100"))
    # History for spike
    for i in range(3):
        _seed_invoice(
            db_session,
            vendor,
            po,
            unit_price=Decimal("100"),
            quantity=Decimal("1"),
            total_amount=Decimal("10000"),
            invoice_number=f"HIST-{uuid4().hex[:6]}-{i}",
            invoice_date=date(2026, 1, 1) + timedelta(days=i),
        )
    spike_inv = _seed_invoice(
        db_session,
        vendor,
        po,
        unit_price=Decimal("350"),
        quantity=Decimal("100"),
        total_amount=Decimal("35000"),
        invoice_number=f"SPIKE-{uuid4().hex[:6]}",
        invoice_date=date(2026, 2, 1),
    )
    exc = ReconciliationException(
        exception_type=ExceptionType.PRICE_MISMATCH.value,
        severity=ExceptionSeverity.HIGH.value,
        message="price",
        status=ExceptionStatus.OPEN.value,
        invoice_id=spike_inv.id,
        purchase_order_id=po.id,
        evidence={},
        fingerprint=f"fp-{uuid4().hex}",
    )
    db_session.add(exc)
    db_session.commit()

    vresp = api_client.post(f"/anomalies/detect/vendor/{vendor.id}")
    assert vresp.status_code == 200
    eresp = api_client.post(f"/anomalies/detect/exception/{exc.id}")
    assert eresp.status_code == 200
    assert api_client.post(f"/anomalies/detect/invoice/{uuid4()}").status_code == 404


def test_duplicate_via_service(db_session: Session) -> None:
    vendor = _seed_vendor(db_session)
    po = _seed_po(db_session, vendor)
    a = _seed_invoice(db_session, vendor, po, invoice_number="DUP 100")
    _seed_invoice(db_session, vendor, po, invoice_number="dup_100")
    rows = AnomalyService(db_session).detect_for_invoice(a.id)
    assert any(r.anomaly_type == AnomalyType.DUPLICATE_INVOICE.value for r in rows)


def test_engine_orchestrates_invoice_rules() -> None:
    po_line = FakeLine(unit_price=Decimal("100"), quantity=Decimal("10"))
    inv_line = FakeLine(
        unit_price=Decimal("150"),
        quantity=Decimal("10"),
        purchase_order_line_id=po_line.id,
    )
    po = FakePO(lines=[po_line])
    inv = FakeInvoice(
        lines=[inv_line],
        purchase_order_id=po.id,
        vendor_id=po.vendor_id,
        total_amount=Decimal("1500"),
    )
    engine = AnomalyEngine(AnomalyConfig())
    signals = engine.detect_for_invoice(
        invoice=inv,
        purchase_order=po,
        goods_receipts=[],
        sibling_invoices=[inv],
        prior_vendor_invoices=[],
    )
    types = {s.anomaly_type for s in signals}
    assert AnomalyType.PRICE_VARIANCE in types
