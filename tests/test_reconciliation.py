"""Deterministic reconciliation engine and service tests (no AI)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ReconciliationException,
    Vendor,
)
from app.domain.enums import (
    ExceptionType,
    GoodsReceiptStatus,
    InvoiceStatus,
    PurchaseOrderStatus,
    ReconciliationStatus,
)
from app.main import app
from app.reconciliation.engine import reconcile
from app.reconciliation.rules import normalize_invoice_number
from app.reconciliation.schemas import (
    DuplicateInvoiceCandidate,
    EngineGoodsReceipt,
    EngineGoodsReceiptLine,
    EngineInvoice,
    EngineInvoiceLine,
    EnginePurchaseOrder,
    EnginePurchaseOrderLine,
    ReconciliationConfig,
    ReconciliationInput,
)
from app.services.reconciliation_service import ReconciliationService

client = TestClient(app)


def _po(
    *,
    lines: list[EnginePurchaseOrderLine] | None = None,
    order_date: date = date(2026, 9, 10),
    vendor_id=None,
) -> EnginePurchaseOrder:
    return EnginePurchaseOrder(
        id=uuid4(),
        po_number=f"PO-{uuid4().hex[:8]}",
        vendor_id=vendor_id or uuid4(),
        order_date=order_date,
        currency="INR",
        lines=lines
        or [
            EnginePurchaseOrderLine(
                id=uuid4(),
                line_number=1,
                description="Item A",
                quantity=Decimal("100"),
                unit_price=Decimal("500"),
                tax_rate=Decimal("0.1800"),
            )
        ],
    )


def _grn(
    po: EnginePurchaseOrder,
    *,
    quantities: list[Decimal],
    receipt_date: date = date(2026, 9, 12),
    po_line: EnginePurchaseOrderLine | None = None,
) -> EngineGoodsReceipt:
    target = po_line or po.lines[0]
    return EngineGoodsReceipt(
        id=uuid4(),
        grn_number=f"GRN-{uuid4().hex[:8]}",
        purchase_order_id=po.id,
        receipt_date=receipt_date,
        lines=[
            EngineGoodsReceiptLine(
                id=uuid4(),
                line_number=1,
                received_quantity=qty,
                purchase_order_line_id=target.id,
            )
            for qty in quantities
        ],
    )


def _invoice(
    po: EnginePurchaseOrder,
    *,
    quantity: Decimal = Decimal("100"),
    unit_price: Decimal = Decimal("500"),
    tax_rate: Decimal = Decimal("0.1800"),
    invoice_date: date = date(2026, 9, 15),
    invoice_number: str | None = None,
    lines: list[EngineInvoiceLine] | None = None,
) -> EngineInvoice:
    if lines is None:
        lines = [
            EngineInvoiceLine(
                id=uuid4(),
                line_number=1,
                description="Item A",
                quantity=quantity,
                unit_price=unit_price,
                tax_rate=tax_rate,
                purchase_order_line_id=po.lines[0].id,
            )
        ]
    return EngineInvoice(
        id=uuid4(),
        invoice_number=invoice_number or f"INV-{uuid4().hex[:8]}",
        vendor_id=po.vendor_id,
        purchase_order_id=po.id,
        invoice_date=invoice_date,
        currency="INR",
        lines=lines,
    )


def test_perfect_match() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, quantity=Decimal("100"), unit_price=Decimal("500"))
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    assert result.status is ReconciliationStatus.MATCHED
    assert result.exception_count == 0


def test_valid_partial_delivery() -> None:
    po = _po()
    grn1 = _grn(po, quantities=[Decimal("40")])
    grn2 = _grn(po, quantities=[Decimal("30")])
    invoice = _invoice(po, quantity=Decimal("70"))
    result = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[grn1, grn2],
            invoice=invoice,
        )
    )
    assert result.status is ReconciliationStatus.MATCHED
    assert result.exception_count == 0
    assert result.summary.total_received_quantity == Decimal("70")


def test_multiple_grns_aggregation() -> None:
    po = _po()
    grns = [
        _grn(po, quantities=[Decimal("40")]),
        _grn(po, quantities=[Decimal("35")]),
        _grn(po, quantities=[Decimal("25")]),
    ]
    invoice = _invoice(po, quantity=Decimal("100"))
    result = reconcile(ReconciliationInput(purchase_order=po, goods_receipts=grns, invoice=invoice))
    assert result.status is ReconciliationStatus.MATCHED
    assert result.summary.total_received_quantity == Decimal("100")


def test_over_received_quantity() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("110")])
    invoice = _invoice(po, quantity=Decimal("100"))
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    types = {e.exception_type for e in result.exceptions}
    assert ExceptionType.QUANTITY_MISMATCH in types
    assert any(e.evidence.get("rule") == "received_gt_ordered" for e in result.exceptions)


def test_over_invoiced_quantity() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("90")])
    invoice = _invoice(po, quantity=Decimal("100"))
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    qty_exc = [e for e in result.exceptions if e.exception_type is ExceptionType.QUANTITY_MISMATCH]
    assert qty_exc
    rules = {e.evidence["rule"] for e in qty_exc}
    assert "invoiced_gt_received" in rules
    assert result.status is ReconciliationStatus.EXCEPTIONS_FOUND


def test_price_mismatch() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, unit_price=Decimal("550"))
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    assert any(e.exception_type is ExceptionType.PRICE_MISMATCH for e in result.exceptions)
    price = next(e for e in result.exceptions if e.exception_type is ExceptionType.PRICE_MISMATCH)
    assert price.evidence["expected_unit_price"] == "500"
    assert price.evidence["billed_unit_price"] == "550"
    assert "absolute_variance" in price.evidence
    assert "percentage_variance" in price.evidence


def test_price_tolerance() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, unit_price=Decimal("505"))  # 1% variance
    within = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[grn],
            invoice=invoice,
            config=ReconciliationConfig(price_tolerance_percent=Decimal("1")),
        )
    )
    assert within.exception_count == 0

    outside = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[grn],
            invoice=invoice,
            config=ReconciliationConfig(price_tolerance_percent=Decimal("0")),
        )
    )
    assert any(e.exception_type is ExceptionType.PRICE_MISMATCH for e in outside.exceptions)


def test_tax_mismatch() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, tax_rate=Decimal("0.1200"))
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    assert any(e.exception_type is ExceptionType.TAX_MISMATCH for e in result.exceptions)


def test_tax_tolerance() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, tax_rate=Decimal("0.1700"))
    within = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[grn],
            invoice=invoice,
            config=ReconciliationConfig(tax_rate_tolerance_percent=Decimal("10")),
        )
    )
    assert not any(e.exception_type is ExceptionType.TAX_MISMATCH for e in within.exceptions)

    outside = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[grn],
            invoice=invoice,
            config=ReconciliationConfig(tax_rate_tolerance_percent=Decimal("0")),
        )
    )
    assert any(e.exception_type is ExceptionType.TAX_MISMATCH for e in outside.exceptions)


def test_identifier_mismatch() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po)
    invoice.lines[0].purchase_order_line_id = uuid4()
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    assert any(e.exception_type is ExceptionType.IDENTIFIER_MISMATCH for e in result.exceptions)


def test_missing_grn() -> None:
    po = _po()
    invoice = _invoice(po)
    result = reconcile(ReconciliationInput(purchase_order=po, goods_receipts=[], invoice=invoice))
    assert result.status is ReconciliationStatus.INCOMPLETE
    assert any(e.exception_type is ExceptionType.MISSING_DOCUMENT for e in result.exceptions)
    assert any(e.evidence.get("missing_document") == "GRN" for e in result.exceptions)
    assert not any(e.exception_type is ExceptionType.QUANTITY_MISMATCH for e in result.exceptions)
    assert not any(e.exception_type is ExceptionType.PRICE_MISMATCH for e in result.exceptions)


def test_missing_po() -> None:
    invoice = EngineInvoice(
        id=uuid4(),
        invoice_number="INV-MISS-PO",
        vendor_id=uuid4(),
        purchase_order_id=None,
        invoice_date=date(2026, 9, 15),
        lines=[
            EngineInvoiceLine(
                id=uuid4(),
                line_number=1,
                quantity=Decimal("1"),
                unit_price=Decimal("10"),
            )
        ],
    )
    result = reconcile(ReconciliationInput(purchase_order=None, invoice=invoice))
    assert result.status is ReconciliationStatus.INCOMPLETE
    assert any(e.evidence.get("missing_document") == "PO" for e in result.exceptions)


def test_missing_invoice() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    result = reconcile(ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=None))
    assert result.status is ReconciliationStatus.INCOMPLETE
    assert any(e.evidence.get("missing_document") == "INVOICE" for e in result.exceptions)


def test_duplicate_invoice() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, invoice_number="INV-100")
    other_id = uuid4()
    result = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[grn],
            invoice=invoice,
            duplicate_candidates=[
                DuplicateInvoiceCandidate(
                    id=other_id,
                    vendor_id=po.vendor_id,
                    invoice_number="inv 100",
                )
            ],
        )
    )
    assert any(e.exception_type is ExceptionType.DUPLICATE_INVOICE for e in result.exceptions)


def test_invoice_identifier_normalization() -> None:
    assert normalize_invoice_number("  INV_100  ") == "inv-100"
    assert normalize_invoice_number("inv 100") == "inv-100"
    assert normalize_invoice_number("INV--100") == "inv-100"


def test_impossible_grn_date() -> None:
    po = _po(order_date=date(2026, 9, 10))
    grn = _grn(po, quantities=[Decimal("100")], receipt_date=date(2026, 9, 8))
    invoice = _invoice(po)
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    assert any(e.exception_type is ExceptionType.DATE_MISMATCH for e in result.exceptions)
    assert any(e.evidence.get("rule") == "grn_date_before_po_date" for e in result.exceptions)


def test_impossible_invoice_date() -> None:
    po = _po(order_date=date(2026, 9, 10))
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, invoice_date=date(2026, 9, 1))
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    assert any(e.evidence.get("rule") == "invoice_date_before_po_date" for e in result.exceptions)


def test_multiple_po_lines_only_affected_line_exception() -> None:
    line1 = EnginePurchaseOrderLine(
        id=uuid4(),
        line_number=1,
        quantity=Decimal("100"),
        unit_price=Decimal("500"),
        tax_rate=Decimal("0.1800"),
    )
    line2 = EnginePurchaseOrderLine(
        id=uuid4(),
        line_number=2,
        quantity=Decimal("50"),
        unit_price=Decimal("200"),
        tax_rate=Decimal("0.1800"),
    )
    po = _po(lines=[line1, line2])
    grn = EngineGoodsReceipt(
        id=uuid4(),
        grn_number="GRN-ML",
        purchase_order_id=po.id,
        receipt_date=date(2026, 9, 12),
        lines=[
            EngineGoodsReceiptLine(
                id=uuid4(),
                line_number=1,
                received_quantity=Decimal("100"),
                purchase_order_line_id=line1.id,
            ),
            EngineGoodsReceiptLine(
                id=uuid4(),
                line_number=2,
                received_quantity=Decimal("50"),
                purchase_order_line_id=line2.id,
            ),
        ],
    )
    invoice = _invoice(
        po,
        lines=[
            EngineInvoiceLine(
                id=uuid4(),
                line_number=1,
                quantity=Decimal("100"),
                unit_price=Decimal("500"),
                tax_rate=Decimal("0.1800"),
                purchase_order_line_id=line1.id,
            ),
            EngineInvoiceLine(
                id=uuid4(),
                line_number=2,
                quantity=Decimal("50"),
                unit_price=Decimal("250"),
                tax_rate=Decimal("0.1800"),
                purchase_order_line_id=line2.id,
            ),
        ],
    )
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    price_exc = [e for e in result.exceptions if e.exception_type is ExceptionType.PRICE_MISMATCH]
    assert len(price_exc) == 1
    assert price_exc[0].evidence["purchase_order_line_id"] == str(line2.id)
    assert price_exc[0].evidence["line_number"] == 2


def test_structured_evidence_correctness() -> None:
    po = _po()
    grn = _grn(po, quantities=[Decimal("100")])
    invoice = _invoice(po, unit_price=Decimal("550"))
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    price = next(e for e in result.exceptions if e.exception_type is ExceptionType.PRICE_MISMATCH)
    for key in (
        "purchase_order_id",
        "purchase_order_line_id",
        "invoice_id",
        "invoice_line_id",
        "expected_unit_price",
        "billed_unit_price",
        "absolute_variance",
        "percentage_variance",
    ):
        assert key in price.evidence


def test_decimal_precision() -> None:
    po = _po(
        lines=[
            EnginePurchaseOrderLine(
                id=uuid4(),
                line_number=1,
                quantity=Decimal("3"),
                unit_price=Decimal("19.9900"),
                tax_rate=Decimal("0.1000"),
            )
        ]
    )
    grn = _grn(po, quantities=[Decimal("3")])
    invoice = _invoice(
        po,
        quantity=Decimal("3"),
        unit_price=Decimal("19.9900"),
        tax_rate=Decimal("0.1000"),
    )
    result = reconcile(
        ReconciliationInput(purchase_order=po, goods_receipts=[grn], invoice=invoice)
    )
    assert result.status is ReconciliationStatus.MATCHED
    assert result.summary.total_ordered_quantity == Decimal("3")


def test_reconciliation_result_status() -> None:
    po = _po()
    matched = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[_grn(po, quantities=[Decimal("100")])],
            invoice=_invoice(po),
        )
    )
    assert matched.status is ReconciliationStatus.MATCHED

    incomplete = reconcile(ReconciliationInput(purchase_order=po, invoice=_invoice(po)))
    assert incomplete.status is ReconciliationStatus.INCOMPLETE

    exceptions = reconcile(
        ReconciliationInput(
            purchase_order=po,
            goods_receipts=[_grn(po, quantities=[Decimal("100")])],
            invoice=_invoice(po, unit_price=Decimal("999")),
        )
    )
    assert exceptions.status is ReconciliationStatus.EXCEPTIONS_FOUND


def test_empty_invalid_input() -> None:
    result = reconcile(ReconciliationInput())
    assert result.status is ReconciliationStatus.INCOMPLETE
    assert result.exception_count >= 1


def _seed_documents(session: Session) -> tuple[PurchaseOrder, Invoice, GoodsReceipt]:
    vendor = Vendor(name="Acme", tax_id=f"TAX-{uuid4().hex[:8]}")
    session.add(vendor)
    session.flush()

    po = PurchaseOrder(
        po_number=f"PO-{uuid4().hex[:8]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
        currency="INR",
        status=PurchaseOrderStatus.OPEN.value,
    )
    session.add(po)
    session.flush()

    po_line = PurchaseOrderLine(
        purchase_order_id=po.id,
        line_number=1,
        description="Widget",
        quantity=Decimal("100"),
        unit_price=Decimal("500"),
        tax_rate=Decimal("0.1800"),
    )
    session.add(po_line)
    session.flush()

    grn = GoodsReceipt(
        grn_number=f"GRN-{uuid4().hex[:8]}",
        purchase_order_id=po.id,
        receipt_date=date(2026, 9, 12),
        status=GoodsReceiptStatus.POSTED.value,
    )
    session.add(grn)
    session.flush()
    session.add(
        GoodsReceiptLine(
            goods_receipt_id=grn.id,
            purchase_order_line_id=po_line.id,
            line_number=1,
            received_quantity=Decimal("90"),
        )
    )

    invoice = Invoice(
        invoice_number=f"INV-{uuid4().hex[:8]}",
        vendor_id=vendor.id,
        purchase_order_id=po.id,
        invoice_date=date(2026, 9, 15),
        currency="INR",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=Decimal("50000"),
        tax_amount=Decimal("9000"),
        total_amount=Decimal("59000"),
    )
    session.add(invoice)
    session.flush()
    session.add(
        InvoiceLine(
            invoice_id=invoice.id,
            purchase_order_line_id=po_line.id,
            line_number=1,
            description="Widget",
            quantity=Decimal("100"),
            unit_price=Decimal("500"),
            tax_rate=Decimal("0.1800"),
        )
    )
    session.commit()
    return po, invoice, grn


def test_persistence_of_exceptions(db_session: Session) -> None:
    po, invoice, _grn_row = _seed_documents(db_session)
    service = ReconciliationService(db_session)
    result = service.run(purchase_order_id=po.id, invoice_id=invoice.id, persist=True)
    assert result.exception_count >= 1

    count = db_session.scalar(select(func.count()).select_from(ReconciliationException))
    assert count is not None
    assert count >= 1
    row = db_session.scalars(select(ReconciliationException)).first()
    assert row is not None
    assert row.fingerprint is not None
    assert isinstance(row.evidence, dict)
    assert row.evidence


def test_rerun_does_not_create_uncontrolled_duplicates(db_session: Session) -> None:
    po, invoice, _grn_row = _seed_documents(db_session)
    service = ReconciliationService(db_session)
    first = service.run(purchase_order_id=po.id, invoice_id=invoice.id, persist=True)
    first_count = db_session.scalar(select(func.count()).select_from(ReconciliationException))
    second = service.run(purchase_order_id=po.id, invoice_id=invoice.id, persist=True)
    second_count = db_session.scalar(select(func.count()).select_from(ReconciliationException))

    assert first.exception_count == second.exception_count
    assert first_count == second_count


def test_api_reconciliation_run(db_session: Session) -> None:
    po, invoice, _grn_row = _seed_documents(db_session)

    def _override_get_db():
        try:
            yield db_session
        finally:
            pass

    from app.db.session import get_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.post(
            "/reconciliation/run",
            json={
                "purchase_order_id": str(po.id),
                "invoice_id": str(invoice.id),
                "persist": True,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] in {"MATCHED", "EXCEPTIONS_FOUND", "INCOMPLETE"}
        assert "exceptions" in body
        assert "summary" in body
    finally:
        app.dependency_overrides.clear()


def test_api_requires_document_id() -> None:
    response = client.post("/reconciliation/run", json={})
    assert response.status_code == 422
