"""Persistence-layer tests for procurement ORM models and Alembic migrations."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings
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
from app.db.session import get_engine, get_session_factory
from app.domain.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    GoodsReceiptStatus,
    InvoiceStatus,
    PurchaseOrderStatus,
)
from tests.conftest import assert_table_exists


def test_database_session_creation(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Application session factory creates usable sessions."""
    db_path = tmp_path / "session.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_session_factory.cache_clear()

    engine = get_engine()
    assert engine is not None
    factory = get_session_factory()
    session = factory()
    try:
        assert session.bind is engine
        assert session.execute(select(1)).scalar_one() == 1
    finally:
        session.close()
        get_settings.cache_clear()
        get_engine.cache_clear()
        get_session_factory.cache_clear()


def test_vendor_creation(db_session: Session) -> None:
    vendor = Vendor(name="Acme Supplies", tax_id="29AAAAA0000A1Z5")
    db_session.add(vendor)
    db_session.commit()

    loaded = db_session.get(Vendor, vendor.id)
    assert loaded is not None
    assert loaded.name == "Acme Supplies"
    assert loaded.tax_id == "29AAAAA0000A1Z5"
    assert loaded.created_at is not None
    assert loaded.updated_at is not None


def test_po_to_po_lines_relationship(db_session: Session) -> None:
    vendor = Vendor(name="Vendor A", tax_id="TAX-PO-1")
    po = PurchaseOrder(
        po_number="PO-1001",
        vendor=vendor,
        order_date=date(2026, 1, 10),
        currency="USD",
        status=PurchaseOrderStatus.OPEN.value,
        lines=[
            PurchaseOrderLine(
                line_number=1,
                description="Widget A",
                quantity=Decimal("10"),
                unit_price=Decimal("25.5000"),
                tax_rate=Decimal("0.1800"),
            ),
            PurchaseOrderLine(
                line_number=2,
                description="Widget B",
                quantity=Decimal("2"),
                unit_price=Decimal("100.0000"),
                tax_rate=Decimal("0.0500"),
            ),
        ],
    )
    db_session.add(po)
    db_session.commit()

    loaded = db_session.get(PurchaseOrder, po.id)
    assert loaded is not None
    assert len(loaded.lines) == 2
    assert loaded.lines[0].purchase_order_id == loaded.id
    assert {line.line_number for line in loaded.lines} == {1, 2}


def test_grn_to_grn_lines_relationship(db_session: Session) -> None:
    vendor = Vendor(name="Vendor B", tax_id="TAX-GRN-1")
    po = PurchaseOrder(
        po_number="PO-2001",
        vendor=vendor,
        order_date=date(2026, 2, 1),
        currency="INR",
        status=PurchaseOrderStatus.OPEN.value,
    )
    po_line = PurchaseOrderLine(
        line_number=1,
        description="Bolt",
        quantity=Decimal("50"),
        unit_price=Decimal("1.2500"),
        tax_rate=Decimal("0.1200"),
    )
    po.lines.append(po_line)
    grn = GoodsReceipt(
        grn_number="GRN-2001",
        purchase_order=po,
        receipt_date=date(2026, 2, 5),
        status=GoodsReceiptStatus.POSTED.value,
        lines=[
            GoodsReceiptLine(
                line_number=1,
                purchase_order_line=po_line,
                received_quantity=Decimal("40.0000"),
            )
        ],
    )
    db_session.add(grn)
    db_session.commit()

    loaded = db_session.get(GoodsReceipt, grn.id)
    assert loaded is not None
    assert len(loaded.lines) == 1
    assert loaded.lines[0].received_quantity == Decimal("40.0000")
    assert loaded.lines[0].purchase_order_line_id == po_line.id


def test_invoice_to_invoice_lines_relationship(db_session: Session) -> None:
    vendor = Vendor(name="Vendor C", tax_id="TAX-INV-1")
    invoice = Invoice(
        invoice_number="INV-3001",
        vendor=vendor,
        invoice_date=date(2026, 3, 1),
        currency="USD",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=Decimal("100.0000"),
        tax_amount=Decimal("18.0000"),
        total_amount=Decimal("118.0000"),
        lines=[
            InvoiceLine(
                line_number=1,
                description="Service fee",
                quantity=Decimal("1"),
                unit_price=Decimal("100.0000"),
                tax_rate=Decimal("0.1800"),
            )
        ],
    )
    db_session.add(invoice)
    db_session.commit()

    loaded = db_session.get(Invoice, invoice.id)
    assert loaded is not None
    assert len(loaded.lines) == 1
    assert loaded.lines[0].invoice_id == loaded.id


def test_vendor_to_po_relationship(db_session: Session) -> None:
    vendor = Vendor(name="Vendor D", tax_id="TAX-VPO-1")
    db_session.add(vendor)
    db_session.flush()
    db_session.add_all(
        [
            PurchaseOrder(
                po_number="PO-4001",
                vendor_id=vendor.id,
                order_date=date(2026, 4, 1),
                currency="USD",
                status=PurchaseOrderStatus.OPEN.value,
            ),
            PurchaseOrder(
                po_number="PO-4002",
                vendor_id=vendor.id,
                order_date=date(2026, 4, 2),
                currency="USD",
                status=PurchaseOrderStatus.CLOSED.value,
            ),
        ]
    )
    db_session.commit()

    loaded = db_session.get(Vendor, vendor.id)
    assert loaded is not None
    assert len(loaded.purchase_orders) == 2
    assert {po.po_number for po in loaded.purchase_orders} == {"PO-4001", "PO-4002"}


def test_vendor_to_invoice_relationship(db_session: Session) -> None:
    vendor = Vendor(name="Vendor E", tax_id="TAX-VINV-1")
    invoice = Invoice(
        invoice_number="INV-5001",
        vendor=vendor,
        invoice_date=date(2026, 5, 1),
        currency="USD",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=Decimal("10.0000"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("10.0000"),
    )
    db_session.add(invoice)
    db_session.commit()

    loaded = db_session.get(Vendor, vendor.id)
    assert loaded is not None
    assert len(loaded.invoices) == 1
    assert loaded.invoices[0].invoice_number == "INV-5001"


def test_monetary_values_remain_decimal(db_session: Session) -> None:
    vendor = Vendor(name="Vendor F", tax_id="TAX-DEC-1")
    po = PurchaseOrder(
        po_number="PO-6001",
        vendor=vendor,
        order_date=date(2026, 6, 1),
        currency="USD",
        status=PurchaseOrderStatus.OPEN.value,
        lines=[
            PurchaseOrderLine(
                line_number=1,
                description="Precision item",
                quantity=Decimal("3"),
                unit_price=Decimal("19.9900"),
                tax_rate=Decimal("0.1000"),
            )
        ],
    )
    invoice = Invoice(
        invoice_number="INV-6001",
        vendor=vendor,
        purchase_order=po,
        invoice_date=date(2026, 6, 2),
        currency="USD",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=Decimal("59.9700"),
        tax_amount=Decimal("5.9970"),
        total_amount=Decimal("65.9670"),
    )
    db_session.add_all([po, invoice])
    db_session.commit()

    loaded_po = db_session.get(PurchaseOrder, po.id)
    loaded_inv = db_session.get(Invoice, invoice.id)
    assert loaded_po is not None and loaded_inv is not None
    assert isinstance(loaded_po.lines[0].unit_price, Decimal)
    assert isinstance(loaded_po.lines[0].quantity, Decimal)
    assert isinstance(loaded_inv.total_amount, Decimal)
    assert loaded_po.lines[0].unit_price == Decimal("19.9900")
    assert loaded_inv.total_amount == Decimal("65.9670")

    unit_price_col = inspect(PurchaseOrderLine).c.unit_price
    assert str(unit_price_col.type) == "NUMERIC(18, 4)"


def test_unique_po_and_invoice_identifiers(db_session: Session) -> None:
    vendor = Vendor(name="Vendor G", tax_id="TAX-UNIQ-1")
    db_session.add(
        PurchaseOrder(
            po_number="PO-DUP",
            vendor=vendor,
            order_date=date(2026, 7, 1),
            currency="USD",
            status=PurchaseOrderStatus.OPEN.value,
        )
    )
    db_session.commit()

    db_session.add(
        PurchaseOrder(
            po_number="PO-DUP",
            vendor=vendor,
            order_date=date(2026, 7, 2),
            currency="USD",
            status=PurchaseOrderStatus.OPEN.value,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        Invoice(
            invoice_number="INV-DUP",
            vendor=vendor,
            invoice_date=date(2026, 7, 3),
            currency="USD",
            status=InvoiceStatus.RECEIVED.value,
            subtotal=Decimal("1"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("1"),
        )
    )
    db_session.commit()

    db_session.add(
        Invoice(
            invoice_number="INV-DUP",
            vendor=vendor,
            invoice_date=date(2026, 7, 4),
            currency="USD",
            status=InvoiceStatus.RECEIVED.value,
            subtotal=Decimal("2"),
            tax_amount=Decimal("0"),
            total_amount=Decimal("2"),
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_reconciliation_exception_persistence(db_session: Session) -> None:
    vendor = Vendor(name="Vendor H", tax_id="TAX-EXC-1")
    po = PurchaseOrder(
        po_number="PO-7001",
        vendor=vendor,
        order_date=date(2026, 8, 1),
        currency="USD",
        status=PurchaseOrderStatus.OPEN.value,
    )
    invoice = Invoice(
        invoice_number="INV-7001",
        vendor=vendor,
        purchase_order=po,
        invoice_date=date(2026, 8, 2),
        currency="USD",
        status=InvoiceStatus.EXCEPTION.value,
        subtotal=Decimal("90"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("90"),
    )
    exc = ReconciliationException(
        exception_type=ExceptionType.PRICE_MISMATCH.value,
        severity=ExceptionSeverity.HIGH.value,
        message="Invoice unit price differs from PO",
        status=ExceptionStatus.OPEN.value,
        purchase_order=po,
        invoice=invoice,
        source_document_ids=[str(po.id), str(invoice.id)],
        evidence={
            "po_unit_price": "100.0000",
            "invoice_unit_price": "90.0000",
            "line_number": 1,
        },
    )
    db_session.add_all([po, invoice, exc])
    db_session.commit()

    loaded = db_session.get(ReconciliationException, exc.id)
    assert loaded is not None
    assert loaded.exception_type == ExceptionType.PRICE_MISMATCH.value
    assert loaded.severity == ExceptionSeverity.HIGH.value
    assert loaded.status == ExceptionStatus.OPEN.value
    assert loaded.purchase_order_id == po.id
    assert loaded.invoice_id == invoice.id
    assert loaded.evidence["invoice_unit_price"] == "90.0000"
    assert loaded.resolved_at is None

    loaded.status = ExceptionStatus.RESOLVED.value
    loaded.resolved_at = datetime.now(UTC)
    db_session.commit()
    assert loaded.resolved_at is not None


def test_foreign_key_relationships(db_session: Session) -> None:
    """Invalid FK references are rejected when foreign keys are enforced."""
    orphan_po = PurchaseOrder(
        po_number="PO-ORPHAN",
        vendor_id=uuid4(),
        order_date=date(2026, 9, 1),
        currency="USD",
        status=PurchaseOrderStatus.OPEN.value,
    )
    db_session.add(orphan_po)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    vendor = Vendor(name="Vendor I", tax_id="TAX-FK-1")
    po = PurchaseOrder(
        po_number="PO-8001",
        vendor=vendor,
        order_date=date(2026, 9, 2),
        currency="USD",
        status=PurchaseOrderStatus.OPEN.value,
    )
    invoice = Invoice(
        invoice_number="INV-8001",
        vendor=vendor,
        purchase_order=po,
        invoice_date=date(2026, 9, 3),
        currency="USD",
        status=InvoiceStatus.RECEIVED.value,
        subtotal=Decimal("5"),
        tax_amount=Decimal("0"),
        total_amount=Decimal("5"),
    )
    db_session.add_all([vendor, po, invoice])
    db_session.commit()

    assert invoice.purchase_order_id == po.id
    assert invoice.vendor_id == vendor.id
    assert po.vendor_id == vendor.id


def test_alembic_migration_creates_schema(migrated_engine: Engine) -> None:
    expected_tables = {
        "vendors",
        "purchase_orders",
        "purchase_order_lines",
        "goods_receipts",
        "goods_receipt_lines",
        "invoices",
        "invoice_lines",
        "reconciliation_exceptions",
        "documents",
        "document_extraction_results",
        "alembic_version",
    }
    tables = set(inspect(migrated_engine).get_table_names())
    assert expected_tables.issubset(tables)
    for name in expected_tables - {"alembic_version"}:
        assert_table_exists(migrated_engine, name)

    factory = sessionmaker(bind=migrated_engine, expire_on_commit=False)
    session = factory()
    try:
        vendor = Vendor(name="Migrated Vendor", tax_id="TAX-MIG-1")
        session.add(vendor)
        session.commit()
        assert session.get(Vendor, vendor.id) is not None
    finally:
        session.close()
