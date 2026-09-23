"""M10.3 read-only procurement workspace queries."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    PurchaseOrder,
    PurchaseOrderLine,
    ReconciliationException,
    Vendor,
)
from app.db.session import get_db
from app.main import app


def _client(db_session: Session) -> TestClient:
    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _seed(db_session: Session) -> None:
    vendor = Vendor(name="Northwind")
    db_session.add(vendor)
    db_session.flush()
    po = PurchaseOrder(
        po_number="PO-100",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 1),
        currency="INR",
        status="OPEN",
    )
    db_session.add(po)
    db_session.flush()
    db_session.add(
        PurchaseOrderLine(
            purchase_order_id=po.id,
            line_number=1,
            description="Cable",
            quantity=Decimal("2"),
            unit_price=Decimal("10"),
        )
    )
    grn = GoodsReceipt(
        grn_number="GRN-100",
        purchase_order_id=po.id,
        receipt_date=date(2026, 9, 2),
        status="POSTED",
    )
    db_session.add(grn)
    db_session.flush()
    db_session.add(
        GoodsReceiptLine(
            goods_receipt_id=grn.id,
            line_number=1,
            received_quantity=Decimal("2"),
        )
    )
    invoice = Invoice(
        invoice_number="INV-100",
        vendor_id=vendor.id,
        purchase_order_id=po.id,
        invoice_date=date(2026, 9, 3),
        currency="INR",
        status="EXCEPTION",
        total_amount=Decimal("25"),
    )
    db_session.add(invoice)
    db_session.flush()
    db_session.add(
        ReconciliationException(
            exception_type="PRICE_MISMATCH",
            severity="HIGH",
            message="Invoice unit price differs from the purchase order.",
            status="OPEN",
            purchase_order_id=po.id,
            goods_receipt_id=grn.id,
            invoice_id=invoice.id,
            fingerprint="ws-ex-1",
            evidence={"expected_unit_price": "10", "actual_unit_price": "12.5"},
            source_document_ids=[],
        )
    )
    db_session.add(
        Document(
            original_filename="vendor-invoice.pdf",
            stored_filename="stored.pdf",
            document_type="INVOICE",
            mime_type="application/pdf",
            file_extension=".pdf",
            file_size=8,
            sha256="a" * 64,
            storage_path="hidden/path",
            status="VALIDATED",
            vendor_id=vendor.id,
            purchase_order_id=po.id,
            invoice_id=invoice.id,
        )
    )
    db_session.flush()


def test_workspace_lists_empty(db_session: Session) -> None:
    client = _client(db_session)
    try:
        assert client.get("/purchase-orders").json()["total"] == 0
        assert client.get("/goods-receipts").json()["total"] == 0
        assert client.get("/invoices").json()["total"] == 0
        body = client.get("/reconciliation/exceptions").json()
        assert body["total"] == 0
        assert body["counts_by_status"]["OPEN"] == 0
    finally:
        app.dependency_overrides.clear()


def test_workspace_lists_filter_and_detail(db_session: Session) -> None:
    _seed(db_session)
    client = _client(db_session)
    try:
        pos = client.get("/purchase-orders", params={"q": "PO-100", "status": "OPEN"})
        assert pos.status_code == 200
        assert pos.json()["items"][0]["vendor_name"] == "Northwind"
        assert pos.json()["items"][0]["line_count"] == 1

        grns = client.get("/goods-receipts", params={"q": "GRN-100"})
        assert grns.json()["items"][0]["po_number"] == "PO-100"

        invoices = client.get("/invoices", params={"q": "INV-100", "limit": 1, "offset": 0})
        amount = str(invoices.json()["items"][0]["total_amount"])
        assert amount.startswith("25")
        assert invoices.json()["items"][0]["po_number"] == "PO-100"
        assert client.get("/invoices", params={"q": "missing"}).json()["total"] == 0

        listed = client.get(
            "/reconciliation/exceptions",
            params={"status": "OPEN", "severity": "HIGH", "q": "INV-100"},
        )
        assert listed.status_code == 200
        item = listed.json()["items"][0]
        assert item["exception_type"] == "PRICE_MISMATCH"
        assert item["po_number"] == "PO-100"
        detail = client.get(f"/reconciliation/exceptions/{item['id']}")
        assert detail.status_code == 200
        assert detail.json()["evidence"]["expected_unit_price"] == "10"
        assert "hidden/path" not in detail.text

        docs = client.get("/documents", params={"q": "vendor-invoice", "limit": 10})
        assert docs.status_code == 200
        assert docs.json()["total"] == 1
        assert docs.json()["items"][0]["status"] == "VALIDATED"
        assert "hidden/path" in docs.text
    finally:
        app.dependency_overrides.clear()
