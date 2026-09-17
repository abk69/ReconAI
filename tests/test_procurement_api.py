"""Structured procurement API and intake service tests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.enums import DocumentType, ReconciliationStatus
from app.main import app
from app.services.document_service import DocumentService
from app.services.procurement_service import (
    ProcurementNotFoundError,
    ProcurementService,
    ProcurementValidationError,
)
from app.services.reconciliation_service import ReconciliationService
from app.storage.local import LocalFileStorage

client = TestClient(app)


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture
def api_client(db_session: Session, storage_root: Path):
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    yield client
    app.dependency_overrides.clear()


def test_create_vendor(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="Acme", tax_id="GSTIN-1")
    assert vendor.name == "Acme"
    loaded = ProcurementService(db_session).get_vendor(vendor.id)
    assert loaded.id == vendor.id


def test_create_po(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V", tax_id=f"T-{uuid4().hex[:6]}")
    po = ProcurementService(db_session).create_purchase_order(
        po_number=f"PO-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
    )
    assert po.vendor_id == vendor.id
    assert po.lines == []


def test_create_po_with_lines(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V", tax_id=f"T-{uuid4().hex[:6]}")
    po = ProcurementService(db_session).create_purchase_order(
        po_number=f"PO-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
        lines=[
            {
                "line_number": 1,
                "description": "Item",
                "quantity": Decimal("100"),
                "unit_price": Decimal("500"),
                "tax_rate": Decimal("0.18"),
            }
        ],
    )
    assert len(po.lines) == 1
    assert po.lines[0].unit_price == Decimal("500")


def test_create_grn(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V", tax_id=f"T-{uuid4().hex[:6]}")
    po = ProcurementService(db_session).create_purchase_order(
        po_number=f"PO-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
        lines=[
            {
                "line_number": 1,
                "quantity": Decimal("10"),
                "unit_price": Decimal("5"),
                "tax_rate": Decimal("0"),
            }
        ],
    )
    grn = ProcurementService(db_session).create_goods_receipt(
        grn_number=f"GRN-{uuid4().hex[:6]}",
        purchase_order_id=po.id,
        receipt_date=date(2026, 9, 12),
    )
    assert grn.purchase_order_id == po.id


def test_create_grn_with_lines(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V", tax_id=f"T-{uuid4().hex[:6]}")
    po = ProcurementService(db_session).create_purchase_order(
        po_number=f"PO-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
        lines=[
            {
                "line_number": 1,
                "quantity": Decimal("10"),
                "unit_price": Decimal("5"),
                "tax_rate": Decimal("0"),
            }
        ],
    )
    grn = ProcurementService(db_session).create_goods_receipt(
        grn_number=f"GRN-{uuid4().hex[:6]}",
        purchase_order_id=po.id,
        receipt_date=date(2026, 9, 12),
        lines=[
            {
                "line_number": 1,
                "received_quantity": Decimal("10"),
                "purchase_order_line_id": po.lines[0].id,
            }
        ],
    )
    assert len(grn.lines) == 1
    assert grn.lines[0].purchase_order_line_id == po.lines[0].id


def test_create_invoice(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V", tax_id=f"T-{uuid4().hex[:6]}")
    invoice = ProcurementService(db_session).create_invoice(
        invoice_number=f"INV-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        invoice_date=date(2026, 9, 15),
        total_amount=Decimal("50"),
    )
    assert invoice.vendor_id == vendor.id


def test_create_invoice_with_lines(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V", tax_id=f"T-{uuid4().hex[:6]}")
    po = ProcurementService(db_session).create_purchase_order(
        po_number=f"PO-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
        lines=[
            {
                "line_number": 1,
                "quantity": Decimal("2"),
                "unit_price": Decimal("25"),
                "tax_rate": Decimal("0.18"),
            }
        ],
    )
    invoice = ProcurementService(db_session).create_invoice(
        invoice_number=f"INV-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        purchase_order_id=po.id,
        invoice_date=date(2026, 9, 15),
        subtotal=Decimal("50"),
        tax_amount=Decimal("9"),
        total_amount=Decimal("59"),
        lines=[
            {
                "line_number": 1,
                "quantity": Decimal("2"),
                "unit_price": Decimal("25"),
                "tax_rate": Decimal("0.18"),
                "purchase_order_line_id": po.lines[0].id,
            }
        ],
    )
    assert len(invoice.lines) == 1


def test_invalid_vendor_reference(db_session: Session) -> None:
    with pytest.raises(ProcurementNotFoundError):
        ProcurementService(db_session).create_purchase_order(
            po_number="PO-X",
            vendor_id=uuid4(),
            order_date=date(2026, 9, 1),
        )


def test_invalid_po_reference(db_session: Session) -> None:
    with pytest.raises(ProcurementNotFoundError):
        ProcurementService(db_session).create_goods_receipt(
            grn_number="GRN-X",
            purchase_order_id=uuid4(),
            receipt_date=date(2026, 9, 1),
        )


def test_invalid_po_line_reference(db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V", tax_id=f"T-{uuid4().hex[:6]}")
    po = ProcurementService(db_session).create_purchase_order(
        po_number=f"PO-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
        lines=[
            {
                "line_number": 1,
                "quantity": Decimal("1"),
                "unit_price": Decimal("1"),
                "tax_rate": Decimal("0"),
            }
        ],
    )
    with pytest.raises(ProcurementValidationError):
        ProcurementService(db_session).create_goods_receipt(
            grn_number=f"GRN-{uuid4().hex[:6]}",
            purchase_order_id=po.id,
            receipt_date=date(2026, 9, 12),
            lines=[
                {
                    "line_number": 1,
                    "received_quantity": Decimal("1"),
                    "purchase_order_line_id": uuid4(),
                }
            ],
        )


def test_get_procurement_records_api(api_client: TestClient) -> None:
    vendor_resp = api_client.post("/vendors", json={"name": "API Vendor", "tax_id": "TAX-API-1"})
    assert vendor_resp.status_code == 201
    vendor_id = vendor_resp.json()["id"]

    get_vendor = api_client.get(f"/vendors/{vendor_id}")
    assert get_vendor.status_code == 200

    po_resp = api_client.post(
        "/purchase-orders",
        json={
            "po_number": f"PO-API-{uuid4().hex[:6]}",
            "vendor_id": vendor_id,
            "order_date": "2026-09-10",
            "currency": "INR",
            "lines": [
                {
                    "line_number": 1,
                    "quantity": "100",
                    "unit_price": "500",
                    "tax_rate": "0.18",
                }
            ],
        },
    )
    assert po_resp.status_code == 201
    po_id = po_resp.json()["id"]
    assert len(po_resp.json()["lines"]) == 1

    get_po = api_client.get(f"/purchase-orders/{po_id}")
    assert get_po.status_code == 200


def test_validation_errors_api(api_client: TestClient) -> None:
    resp = api_client.post("/vendors", json={"name": ""})
    assert resp.status_code == 422

    resp = api_client.post(
        "/purchase-orders",
        json={
            "po_number": "PO-BAD",
            "vendor_id": str(uuid4()),
            "order_date": "2026-09-10",
        },
    )
    assert resp.status_code == 404


def test_end_to_end_intake_to_reconciliation(db_session: Session, storage_root: Path) -> None:
    """Vendor → PO → GRN → Invoice → documents → reconciliation still works."""
    procurement = ProcurementService(db_session)
    vendor = procurement.create_vendor(name="E2E Vendor", tax_id=f"T-{uuid4().hex[:6]}")
    po = procurement.create_purchase_order(
        po_number=f"PO-E2E-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 10),
        currency="INR",
        lines=[
            {
                "line_number": 1,
                "description": "Widget",
                "quantity": Decimal("100"),
                "unit_price": Decimal("500"),
                "tax_rate": Decimal("0.18"),
            }
        ],
    )
    grn = procurement.create_goods_receipt(
        grn_number=f"GRN-E2E-{uuid4().hex[:6]}",
        purchase_order_id=po.id,
        receipt_date=date(2026, 9, 12),
        lines=[
            {
                "line_number": 1,
                "received_quantity": Decimal("100"),
                "purchase_order_line_id": po.lines[0].id,
            }
        ],
    )
    invoice = procurement.create_invoice(
        invoice_number=f"INV-E2E-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        purchase_order_id=po.id,
        invoice_date=date(2026, 9, 15),
        currency="INR",
        subtotal=Decimal("50000"),
        tax_amount=Decimal("9000"),
        total_amount=Decimal("59000"),
        lines=[
            {
                "line_number": 1,
                "quantity": Decimal("100"),
                "unit_price": Decimal("500"),
                "tax_rate": Decimal("0.18"),
                "purchase_order_line_id": po.lines[0].id,
            }
        ],
    )

    docs = DocumentService(db_session, storage=LocalFileStorage(storage_root))
    po_doc, _ = docs.upload(
        filename="po.pdf",
        content_type="application/pdf",
        data=b"%PDF e2e po",
        document_type=DocumentType.PO,
        vendor_id=vendor.id,
        purchase_order_id=po.id,
    )
    inv_doc, _ = docs.upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        data=b"%PDF e2e invoice",
        document_type=DocumentType.INVOICE,
        vendor_id=vendor.id,
        invoice_id=invoice.id,
        purchase_order_id=po.id,
    )
    assert po_doc.purchase_order_id == po.id
    assert inv_doc.invoice_id == invoice.id
    assert grn.id is not None

    result = ReconciliationService(db_session).run(
        purchase_order_id=po.id,
        invoice_id=invoice.id,
        persist=True,
    )
    assert result.status is ReconciliationStatus.MATCHED
    assert result.exception_count == 0
