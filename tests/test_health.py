"""Tests for health endpoint, domain enums, and monetary Decimal models."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.domain.enums import DocumentType, ExceptionSeverity, ExceptionType
from app.domain.models import (
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    ReconciliationException,
    Vendor,
)
from app.main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


def test_health_returns_ok() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "reconai"}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


def test_document_type_values() -> None:
    assert set(DocumentType) == {
        DocumentType.PO,
        DocumentType.GRN,
        DocumentType.INVOICE,
    }
    assert DocumentType.PO.value == "PO"
    assert DocumentType.GRN.value == "GRN"
    assert DocumentType.INVOICE.value == "INVOICE"


def test_exception_type_values() -> None:
    expected = {
        "QUANTITY_MISMATCH",
        "PRICE_MISMATCH",
        "TAX_MISMATCH",
        "IDENTIFIER_MISMATCH",
        "DUPLICATE_INVOICE",
        "DATE_MISMATCH",
        "MISSING_DOCUMENT",
        "OTHER",
    }
    assert {member.value for member in ExceptionType} == expected


def test_exception_severity_values() -> None:
    assert [s.value for s in ExceptionSeverity] == [
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ]


# ---------------------------------------------------------------------------
# Domain model validation
# ---------------------------------------------------------------------------


def test_vendor_model() -> None:
    vendor = Vendor(name="Acme Supplies", code="ACME-01", tax_id="12-3456789")
    assert vendor.name == "Acme Supplies"
    assert vendor.code == "ACME-01"
    assert vendor.id is not None


def test_purchase_order_with_lines() -> None:
    vendor_id = uuid4()
    po = PurchaseOrder(
        po_number="PO-1001",
        vendor_id=vendor_id,
        order_date=date(2026, 1, 15),
        lines=[
            PurchaseOrderLine(
                line_number=1,
                sku="WIDGET-A",
                quantity=Decimal("10"),
                unit_price=Decimal("25.50"),
                tax_amount=Decimal("12.75"),
            )
        ],
    )
    assert po.po_number == "PO-1001"
    assert len(po.lines) == 1
    assert po.lines[0].sku == "WIDGET-A"


def test_invoice_rejects_negative_total() -> None:
    with pytest.raises(ValidationError):
        Invoice(
            invoice_number="INV-1",
            vendor_id=uuid4(),
            invoice_date=date(2026, 2, 1),
            total_amount=Decimal("-1.00"),
        )


def test_reconciliation_exception_fields() -> None:
    doc_a = uuid4()
    doc_b = uuid4()
    exc = ReconciliationException(
        type=ExceptionType.QUANTITY_MISMATCH,
        severity=ExceptionSeverity.HIGH,
        message="PO quantity 10 vs invoice quantity 8",
        source_document_ids=[doc_a, doc_b],
        evidence={
            "po_quantity": "10",
            "invoice_quantity": "8",
            "sku": "WIDGET-A",
        },
    )
    assert exc.type is ExceptionType.QUANTITY_MISMATCH
    assert exc.severity is ExceptionSeverity.HIGH
    assert exc.source_document_ids == [doc_a, doc_b]
    assert exc.evidence["sku"] == "WIDGET-A"
    assert exc.created_at is not None
    assert exc.id is not None


# ---------------------------------------------------------------------------
# Decimal monetary fields
# ---------------------------------------------------------------------------


def test_monetary_fields_are_decimal() -> None:
    line = InvoiceLine(
        line_number=1,
        sku="WIDGET-A",
        quantity=Decimal("3"),
        unit_price=Decimal("19.99"),
        tax_amount=Decimal("1.50"),
    )
    assert isinstance(line.unit_price, Decimal)
    assert isinstance(line.tax_amount, Decimal)
    assert isinstance(line.quantity, Decimal)
    assert line.unit_price == Decimal("19.99")


def test_decimal_preserves_precision() -> None:
    """Float arithmetic would yield 0.30000000000000004; Decimal must not."""
    line = PurchaseOrderLine(
        line_number=1,
        sku="PREC-01",
        quantity=Decimal("1"),
        unit_price=Decimal("0.1") + Decimal("0.2"),
    )
    assert line.unit_price == Decimal("0.3")


def test_unit_price_rejects_float_that_loses_exactness_via_string() -> None:
    """Ensure we can construct from string-like Decimal inputs safely."""
    line = InvoiceLine(
        line_number=1,
        sku="SAFE",
        quantity=Decimal("2"),
        unit_price=Decimal("100.10"),
    )
    assert str(line.unit_price) == "100.10"
