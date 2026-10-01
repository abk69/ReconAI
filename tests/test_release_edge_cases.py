"""Ambiguous fields, missing-value phrases, and shared purchase-order summaries."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import (
    GoodsReceipt,
    Invoice,
    PurchaseOrder,
    ReconciliationException,
)
from app.domain.enums import (
    ExceptionType,
    ExtractionOutcome,
    GoodsReceiptStatus,
    InvoiceStatus,
    PurchaseOrderStatus,
    ReconciliationStatus,
)
from app.extraction.base import read_labelled_field
from app.extraction.normalizer import is_missing_value, normalize_business_value
from app.services.document_service import DocumentService
from app.services.document_understanding_service import DocumentUnderstandingService
from app.services.promotion_service import PromotionNotAllowedError, PromotionService
from app.services.reconciliation_service import ReconciliationService
from app.services.review_service import ReviewService, ReviewValidationError
from app.storage.local import LocalFileStorage
from tests.test_validation_workflow import (
    _approve_and_promote,
    _goods_receipt,
    _invoice,
    _purchase_order,
    _understand,
)

_MISSING_PHRASES = (
    "NOT PROVIDED",
    "NOT AVAILABLE",
    "N/A",
    "NA",
    "NONE",
    "NULL",
    "UNKNOWN",
    "NOT SPECIFIED",
    "NOT APPLICABLE",
    "-",
    "--",
    "",
)
_GARBAGE = {"T", "N", "NO", "NOT", "NA", "NONE"}


@pytest.fixture
def workflow(db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "documents"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    storage = LocalFileStorage(root)
    docs = DocumentService(db_session, storage=storage)
    understanding = DocumentUnderstandingService(db_session, storage=storage)
    reviews = ReviewService(db_session)
    promotion = PromotionService(db_session)
    yield docs, understanding, reviews, promotion
    get_settings.cache_clear()


def _ambiguous_invoice() -> str:
    return (
        "NORTHSTAR INDUSTRIAL SUPPLY\n"
        "INVOICE\n"
        "INVOICE NUMBER\n"
        "INV-1005 / INV-100S\n"
        "INVOICE DATE\n"
        "2026-09-22 or 2026-09-23\n"
        "VENDOR\n"
        "Northstar Industrial Supply\n"
        "VENDOR ID\n"
        "V-100\n"
        "PURCHASE ORDER\n"
        "PO-5001 or PO-500I\n"
        "CURRENCY\n"
        "USD\n"
        "SKU / ITEM\n"
        "DESCRIPTION\n"
        "QTY\n"
        "UNIT\n"
        "PRICE\n"
        "AMOUNT\n"
        "SKU-101\n"
        "Industrial gloves\n"
        "10\n"
        "EA\n"
        "12.00\n"
        "120.00\n"
        "TOTAL\n"
        "120.00\n"
    )


def _missing_po_invoice() -> str:
    return (
        "NORTHSTAR INDUSTRIAL SUPPLY\n"
        "INVOICE\n"
        "INVOICE NUMBER\n"
        "INV-1004\n"
        "INVOICE DATE\n"
        "2026-09-21\n"
        "VENDOR\n"
        "Northstar Industrial Supply\n"
        "VENDOR ID\n"
        "NOT PROVIDED\n"
        "PURCHASE ORDER\n"
        "NOT PROVIDED\n"
        "CURRENCY\n"
        "USD\n"
        "SKU / ITEM\n"
        "DESCRIPTION\n"
        "QTY\n"
        "UNIT\n"
        "PRICE\n"
        "AMOUNT\n"
        "SKU-101\n"
        "Industrial gloves\n"
        "10\n"
        "EA\n"
        "12.00\n"
        "120.00\n"
        "TOTAL\n"
        "120.00\n"
    )


def _task_for(reviews: ReviewService, document_id):
    tasks = reviews.list_tasks(document_id=document_id)
    assert len(tasks) == 1
    return tasks[0]


@pytest.mark.parametrize("phrase", _MISSING_PHRASES)
def test_missing_phrases_never_become_partial_identifiers(phrase: str) -> None:
    assert is_missing_value(phrase) is True
    assert normalize_business_value(phrase) is None
    labelled = f"PO Number: {phrase}\n" if phrase else "PO Number:\n"
    stacked = f"PURCHASE ORDER\n{phrase}\n" if phrase else "PURCHASE ORDER\n"
    for text in (labelled, stacked):
        found = read_labelled_field(text, "po_number")
        value = None if found is None else found.value
        assert value is None
        assert value not in _GARBAGE


def test_repeated_labels_are_not_treated_as_conflicts() -> None:
    found = read_labelled_field(
        "INVOICE NUMBER\nINV-1001\nINVOICE NUMBER\nINV-9999\n",
        "invoice_number",
    )
    assert found is not None
    assert found.value == "INV-1001"
    assert found.alternatives == []


def test_same_line_conflicts_keep_every_candidate() -> None:
    number = read_labelled_field("INVOICE NUMBER\nINV-1005 / INV-100S\n", "invoice_number")
    dated = read_labelled_field("INVOICE DATE\n2026-09-22 or 2026-09-23\n", "invoice_date")
    po = read_labelled_field("PURCHASE ORDER\nPO-5001 or PO-500I\n", "po_number")
    assert number is not None and number.value is None
    assert number.alternatives == ["INV-1005", "INV-100S"]
    assert dated is not None and dated.value is None
    assert dated.alternatives == ["2026-09-22", "2026-09-23"]
    assert po is not None and po.value is None
    assert po.alternatives == ["PO-5001", "PO-500I"]


def test_ambiguous_invoice_requires_review_then_matches(workflow, db_session: Session) -> None:
    docs, understanding, reviews, promotion = workflow
    po_row, _, _ = _understand(docs, understanding, "02_purchase_order.pdf", _purchase_order())
    grn_row, _, _ = _understand(docs, understanding, "03_goods_receipt.pdf", _goods_receipt())
    _approve_and_promote(po_row.id, reviews, promotion, db_session)
    _approve_and_promote(grn_row.id, reviews, promotion, db_session)

    row, _, result = _understand(
        docs, understanding, "07_ambiguous_fields_invoice.pdf", _ambiguous_invoice()
    )
    assert result.outcome is ExtractionOutcome.REVIEW_REQUIRED
    assert result.message == "Ambiguous fields require review."
    candidate = result.candidate or {}
    assert candidate.get("invoice_number") is None
    assert candidate.get("invoice_date") is None
    assert candidate.get("po_number") is None
    messages = {
        issue.message
        for issue in result.validation.issues
        if issue.code == "AMBIGUOUS_FIELD"
    }
    assert messages == {
        "Invoice number: INV-1005 / INV-100S",
        "Invoice date: 2026-09-22 / 2026-09-23",
        "PO number: PO-5001 / PO-500I",
    }
    db_session.refresh(row)
    assert row.invoice_id is None

    task = _task_for(reviews, row.id)
    with pytest.raises(ReviewValidationError):
        reviews.approve(task.id, reviewer="qa")
    with pytest.raises(PromotionNotAllowedError):
        promotion.promote(task.id)

    reviews.correct(
        task.id,
        corrections=[
            {"field_path": "invoice_number", "corrected_value": "INV-1005"},
            {"field_path": "invoice_date", "corrected_value": "2026-09-22"},
            {"field_path": "po_number", "corrected_value": "PO-5001"},
        ],
        reviewer="qa",
    )
    reviews.approve(task.id, reviewer="qa")
    promotion.promote(task.id)
    db_session.refresh(row)
    assert row.invoice_id is not None
    run = ReconciliationService(db_session).run(invoice_id=row.invoice_id, persist=True)
    assert run.status is ReconciliationStatus.MATCHED
    saved = db_session.get(Invoice, row.invoice_id)
    assert saved is not None
    db_session.refresh(saved)
    assert saved.status == InvoiceStatus.MATCHED.value
    assert saved.invoice_number == "INV-1005"
    assert saved.purchase_order_id is not None


def test_not_provided_stays_missing_and_does_not_link_a_purchase_order(
    workflow, db_session: Session
) -> None:
    docs, understanding, reviews, promotion = workflow
    row, _, result = _understand(
        docs, understanding, "06_missing_fields_invoice.pdf", _missing_po_invoice()
    )
    assert result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    candidate = result.candidate or {}
    assert candidate.get("po_number") is None
    assert candidate.get("vendor_name") == "Northstar Industrial Supply"
    assert candidate.get("invoice_number") == "INV-1004"
    dumped = repr(candidate)
    assert "'po_number': 'T'" not in dumped
    assert "'po_number': 'NOT PROVIDED'" not in dumped

    _approve_and_promote(row.id, reviews, promotion, db_session)
    db_session.refresh(row)
    invoice = db_session.get(Invoice, row.invoice_id)
    assert invoice is not None
    assert invoice.purchase_order_id is None
    invented = db_session.scalars(
        select(PurchaseOrder).where(
            PurchaseOrder.po_number.in_(["T", "N", "NO", "NOT", "NOT PROVIDED"])
        )
    ).all()
    assert invented == []
    facts = docs.workspace_facts([row.id])
    assert facts[row.id]["po_number"] is None
    assert facts[row.id]["reconciliation_status"] is None


def _invoice_text(number: str) -> str:
    if number == "INV-1002":
        return _invoice(number, price="13.50", amount="135.00", total="175.00")
    if number == "INV-1003":
        return _invoice(number, qty="12", amount="144.00", total="184.00")
    return _invoice(number)


def _reconcile_set(workflow, db_session: Session, order: list[str]):
    docs, understanding, reviews, promotion = workflow
    po_row, _, _ = _understand(docs, understanding, "02_purchase_order.pdf", _purchase_order())
    grn_row, _, _ = _understand(docs, understanding, "03_goods_receipt.pdf", _goods_receipt())
    _approve_and_promote(po_row.id, reviews, promotion, db_session)
    _approve_and_promote(grn_row.id, reviews, promotion, db_session)
    ambiguous_row, _, ambiguous = _understand(
        docs, understanding, "07_ambiguous_fields_invoice.pdf", _ambiguous_invoice()
    )
    assert ambiguous.outcome is ExtractionOutcome.REVIEW_REQUIRED

    rows = {}
    for number in order:
        row, _, result = _understand(docs, understanding, f"{number}.pdf", _invoice_text(number))
        assert result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
        _approve_and_promote(row.id, reviews, promotion, db_session)
        db_session.refresh(row)
        ReconciliationService(db_session).run(invoice_id=row.invoice_id, persist=True)
        rows[number] = row

    purchase_order = db_session.scalar(
        select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-5001")
    )
    receipt = db_session.scalar(
        select(GoodsReceipt).where(GoodsReceipt.grn_number == "GRN-7001")
    )
    assert purchase_order is not None
    assert receipt is not None
    assert purchase_order.status == PurchaseOrderStatus.OPEN.value
    assert receipt.status == GoodsReceiptStatus.POSTED.value

    expected = {
        "INV-1001": (InvoiceStatus.MATCHED.value, set()),
        "INV-1002": (InvoiceStatus.EXCEPTION.value, {ExceptionType.PRICE_MISMATCH.value}),
        "INV-1003": (InvoiceStatus.EXCEPTION.value, {ExceptionType.QUANTITY_MISMATCH.value}),
    }
    for number, (status, required) in expected.items():
        invoice = db_session.get(Invoice, rows[number].invoice_id)
        assert invoice is not None
        db_session.refresh(invoice)
        assert invoice.status == status
        found = set(
            db_session.scalars(
                select(ReconciliationException.exception_type).where(
                    ReconciliationException.invoice_id == invoice.id
                )
            ).all()
        )
        assert required <= found
        if number == "INV-1001":
            assert found == set()
        if number == "INV-1002":
            assert ExceptionType.QUANTITY_MISMATCH.value not in found
        if number == "INV-1003":
            assert ExceptionType.PRICE_MISMATCH.value not in found

    facts = docs.workspace_facts(
        [po_row.id, grn_row.id, ambiguous_row.id, *[item.id for item in rows.values()]]
    )
    summary = "3 related invoices — 1 matched, 2 with problems"
    assert facts[po_row.id]["related_invoice_summary"] == summary
    assert facts[grn_row.id]["related_invoice_summary"] == summary
    assert facts[po_row.id]["reconciliation_status"] is None
    assert facts[grn_row.id]["reconciliation_status"] is None
    assert facts[rows["INV-1001"].id]["reconciliation_status"] == InvoiceStatus.MATCHED.value
    assert facts[rows["INV-1002"].id]["reconciliation_status"] == InvoiceStatus.EXCEPTION.value
    assert facts[rows["INV-1003"].id]["reconciliation_status"] == InvoiceStatus.EXCEPTION.value
    assert facts[ambiguous_row.id]["reconciliation_status"] is None
    assert facts[ambiguous_row.id]["ambiguity_summary"]
    assert "INV-1005" in (facts[ambiguous_row.id]["ambiguity_summary"] or "")
    db_session.refresh(ambiguous_row)
    assert ambiguous_row.invoice_id is None


def test_shared_po_summary_after_clean_then_price_then_quantity(
    workflow, db_session: Session
) -> None:
    _reconcile_set(workflow, db_session, ["INV-1001", "INV-1002", "INV-1003"])


def test_shared_po_summary_after_quantity_then_clean_then_price(
    workflow, db_session: Session
) -> None:
    _reconcile_set(workflow, db_session, ["INV-1003", "INV-1001", "INV-1002"])
