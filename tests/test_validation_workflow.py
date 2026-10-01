"""Clean stacked-layout documents pass validation; invalid candidates stay blocked."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import GoodsReceipt, Invoice, PurchaseOrder
from app.domain.enums import (
    DocumentStatus,
    DocumentType,
    ExceptionType,
    ExtractionOutcome,
    InvoiceStatus,
    ReconciliationStatus,
    ReviewStatus,
)
from app.services.document_service import DocumentService
from app.services.document_understanding_service import DocumentUnderstandingService
from app.services.promotion_service import (
    PromotionNotAllowedError,
    PromotionService,
    PromotionValidationError,
)
from app.services.reconciliation_service import ReconciliationService
from app.services.review_service import ReviewService, ReviewValidationError
from app.storage.local import LocalFileStorage

_LINES = (
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
    "SKU-202\n"
    "Safety goggles\n"
    "5\n"
    "EA\n"
    "8.00\n"
    "40.00\n"
)


def _make_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        if line.strip():
            page.insert_text((72, y), line)
            y += 14
    data = doc.tobytes()
    doc.close()
    return data


def _invoice(
    number: str,
    *,
    qty: str = "10",
    price: str = "12.00",
    amount: str = "120.00",
    total: str = "160.00",
) -> str:
    return (
        "NORTHSTAR INDUSTRIAL SUPPLY\n"
        f"INVOICE {number}\n"
        "INVOICE NUMBER\n"
        f"{number}\n"
        "INVOICE DATE\n"
        "2026-09-15\n"
        "VENDOR\n"
        "Northstar Industrial Supply\n"
        "PURCHASE ORDER\n"
        "PO-5001\n"
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
        f"{qty}\n"
        "EA\n"
        f"{price}\n"
        f"{amount}\n"
        "SKU-202\n"
        "Safety goggles\n"
        "5\n"
        "EA\n"
        "8.00\n"
        "40.00\n"
        "SUBTOTAL\n"
        f"{total}\n"
        "TAX\n"
        "0.00\n"
        "TOTAL\n"
        f"{total}\n"
    )


def _purchase_order() -> str:
    return (
        "NORTHSTAR INDUSTRIAL SUPPLY\n"
        "PURCHASE ORDER PO-5001\n"
        "PURCHASE ORDER\n"
        "PO-5001\n"
        "ORDER DATE\n"
        "2026-09-01\n"
        "VENDOR\n"
        "Northstar Industrial Supply\n"
        "CURRENCY\n"
        "USD\n"
        f"{_LINES}"
        "ORDER TOTAL\n"
        "160.00\n"
    )


def _goods_receipt() -> str:
    return (
        "NORTHSTAR INDUSTRIAL SUPPLY\n"
        "GOODS RECEIPT GRN-7001\n"
        "RECEIPT NUMBER\n"
        "GRN-7001\n"
        "RECEIVED DATE\n"
        "2026-09-18\n"
        "VENDOR\n"
        "Northstar Industrial Supply\n"
        "PURCHASE ORDER\n"
        "PO-5001\n"
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
        "0.00\n"
        "0.00\n"
        "SKU-202\n"
        "Safety goggles\n"
        "5\n"
        "EA\n"
        "0.00\n"
        "0.00\n"
        "RECEIVED LINES\n"
        "2\n"
    )


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


def _understand(
    docs,
    understanding,
    filename: str,
    text: str,
    document_type: DocumentType | None = None,
):
    row, duplicate = docs.upload(
        filename=filename,
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=document_type,
    )
    result = understanding.understand(row.id)
    return row, duplicate, result


def _approve_and_promote(docs_row_id, reviews, promotion, session):
    from app.db.models import DocumentExtractionResult

    extraction = session.scalar(
        select(DocumentExtractionResult).where(DocumentExtractionResult.document_id == docs_row_id)
    )
    assert extraction is not None
    task = reviews.create_review_task(
        document_id=docs_row_id,
        extraction_result_id=extraction.id,
    )
    assert task.status == ReviewStatus.PENDING.value
    with pytest.raises(PromotionNotAllowedError):
        promotion.promote(task.id)
    reviews.approve(task.id, reviewer="qa")
    promoted = promotion.promote(task.id)
    again = promotion.promote(task.id)
    assert again.promoted_entity_id == promoted.promoted_entity_id
    return promoted


def test_clean_stacked_invoice_po_and_grn_match(workflow, db_session: Session) -> None:
    docs, understanding, reviews, promotion = workflow
    po_row, _, po_result = _understand(
        docs, understanding, "02_purchase_order.pdf", _purchase_order()
    )
    assert po_result.detected_type is DocumentType.PO
    assert po_result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    assert po_result.candidate["po_number"] == "PO-5001"
    assert po_result.candidate["currency"] == "USD"
    assert len(po_result.candidate["lines"]) == 2
    assert po_result.candidate["lines"][0]["reference"] == "SKU-101"
    assert po_result.candidate["lines"][0]["quantity"] == "10"
    assert po_result.candidate["lines"][0]["unit_price"] == "12.00"

    grn_row, _, grn_result = _understand(
        docs, understanding, "03_goods_receipt.pdf", _goods_receipt()
    )
    assert grn_result.detected_type is DocumentType.GRN
    assert grn_result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    assert grn_result.candidate["grn_number"] == "GRN-7001"
    assert grn_result.candidate["po_number"] == "PO-5001"
    assert grn_result.candidate["lines"][1]["reference"] == "SKU-202"
    assert grn_result.candidate["lines"][1]["quantity"] == "5"

    invoice_row, _, invoice_result = _understand(
        docs, understanding, "01_clean_invoice.pdf", _invoice("INV-1001")
    )
    assert invoice_result.detected_type is DocumentType.INVOICE
    assert invoice_result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    assert invoice_result.candidate["invoice_number"] == "INV-1001"
    assert invoice_result.candidate["po_number"] == "PO-5001"
    assert invoice_result.candidate["currency"] == "USD"
    assert invoice_result.candidate["total_amount"] == "160.00"
    assert invoice_result.validation.is_valid is True

    _approve_and_promote(po_row.id, reviews, promotion, db_session)
    _approve_and_promote(grn_row.id, reviews, promotion, db_session)
    invoice_task = _approve_and_promote(invoice_row.id, reviews, promotion, db_session)
    assert db_session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1
    assert db_session.scalar(select(func.count()).select_from(GoodsReceipt)) == 1
    assert db_session.scalar(select(func.count()).select_from(Invoice)) == 1

    db_session.refresh(invoice_row)
    result = ReconciliationService(db_session).run(invoice_id=invoice_row.invoice_id, persist=True)
    assert result.status is ReconciliationStatus.MATCHED
    assert result.exceptions == []
    saved_invoice = db_session.get(Invoice, invoice_row.invoice_id)
    assert saved_invoice is not None
    db_session.refresh(saved_invoice)
    assert saved_invoice.status == InvoiceStatus.MATCHED.value
    assert invoice_task.promoted_entity_id == invoice_row.invoice_id


def test_price_and_quantity_mismatches_still_exception(workflow, db_session: Session) -> None:
    docs, understanding, reviews, promotion = workflow
    po_row, _, _ = _understand(docs, understanding, "02_purchase_order.pdf", _purchase_order())
    grn_row, _, _ = _understand(docs, understanding, "03_goods_receipt.pdf", _goods_receipt())
    _approve_and_promote(po_row.id, reviews, promotion, db_session)
    _approve_and_promote(grn_row.id, reviews, promotion, db_session)

    price_row, _, price_result = _understand(
        docs,
        understanding,
        "04_price_mismatch_invoice.pdf",
        _invoice("INV-1002", price="13.50", amount="135.00", total="175.00"),
    )
    assert price_result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    assert price_result.candidate["lines"][0]["unit_price"] == "13.50"
    _approve_and_promote(price_row.id, reviews, promotion, db_session)
    db_session.refresh(price_row)
    price_run = ReconciliationService(db_session).run(invoice_id=price_row.invoice_id, persist=True)
    price_types = {item.exception_type for item in price_run.exceptions}
    assert ExceptionType.PRICE_MISMATCH in price_types
    assert price_run.status is ReconciliationStatus.EXCEPTIONS_FOUND
    price_invoice = db_session.get(Invoice, price_row.invoice_id)
    assert price_invoice is not None
    db_session.refresh(price_invoice)
    assert price_invoice.status == InvoiceStatus.EXCEPTION.value

    qty_row, _, qty_result = _understand(
        docs,
        understanding,
        "05_quantity_mismatch_invoice.pdf",
        _invoice("INV-1003", qty="12", amount="144.00", total="184.00"),
    )
    assert qty_result.candidate["lines"][0]["quantity"] == "12"
    _approve_and_promote(qty_row.id, reviews, promotion, db_session)
    db_session.refresh(qty_row)
    qty_run = ReconciliationService(db_session).run(invoice_id=qty_row.invoice_id, persist=True)
    qty_types = {item.exception_type for item in qty_run.exceptions}
    assert ExceptionType.QUANTITY_MISMATCH in qty_types


def test_duplicate_upload_does_not_create_a_second_invoice(workflow, db_session: Session) -> None:
    docs, understanding, reviews, promotion = workflow
    text = _invoice("INV-1001")
    payload = _make_pdf(text)
    first, duplicate = docs.upload(
        filename="01_clean_invoice.pdf",
        content_type="application/pdf",
        data=payload,
    )
    assert duplicate is False
    result = understanding.understand(first.id)
    assert result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    _approve_and_promote(first.id, reviews, promotion, db_session)
    second, duplicate_again = docs.upload(
        filename="01_clean_invoice_copy.pdf",
        content_type="application/pdf",
        data=payload,
    )
    assert duplicate_again is True
    assert second.id == first.id
    assert db_session.scalar(select(func.count()).select_from(Invoice)) == 1


def test_invalid_documents_stay_blocked(workflow, db_session: Session) -> None:
    docs, understanding, reviews, promotion = workflow

    missing, _, missing_result = _understand(
        docs,
        understanding,
        "invoice-missing.pdf",
        "INVOICE NUMBER\nINV-9\nINVOICE DATE\n2026-09-15\nWidget 1 10.00\n",
        DocumentType.INVOICE,
    )
    assert missing_result.outcome is ExtractionOutcome.VALIDATION_FAILED
    assert "MISSING_VENDOR" in {issue.code for issue in missing_result.validation.issues}

    dated, _, dated_result = _understand(
        docs,
        understanding,
        "invoice-date.pdf",
        "INVOICE NUMBER\nINV-DATE\nVENDOR\nAcme\nINVOICE DATE\n32/13/2026\nWidget 1 10.00\n",
        DocumentType.INVOICE,
    )
    assert dated_result.outcome is ExtractionOutcome.VALIDATION_FAILED
    assert "MISSING_INVOICE_DATE" in {issue.code for issue in dated_result.validation.issues}

    priced, _, priced_result = _understand(
        docs,
        understanding,
        "invoice-price.pdf",
        "INVOICE NUMBER\nINV-PRICE\nVENDOR\nAcme\nINVOICE DATE\n2026-09-15\n"
        "SKU / ITEM\nDESCRIPTION\nQTY\nUNIT\nPRICE\nAMOUNT\n"
        "SKU-1\nWidget\n2\nEA\ntwelve\n0\n",
        DocumentType.INVOICE,
    )
    assert priced_result.outcome is ExtractionOutcome.VALIDATION_FAILED
    assert "INVALID_PRICE" in {issue.code for issue in priced_result.validation.issues}

    lined, _, lined_result = _understand(
        docs,
        understanding,
        "invoice-line.pdf",
        "INVOICE NUMBER\nINV-LINE\nVENDOR\nAcme\nINVOICE DATE\n2026-09-15\nWidget 0 10.00\n",
        DocumentType.INVOICE,
    )
    assert lined_result.outcome is ExtractionOutcome.VALIDATION_FAILED
    assert "INVALID_QUANTITY" in {issue.code for issue in lined_result.validation.issues}

    ambiguous, _, ambiguous_result = _understand(
        docs,
        understanding,
        "notes.pdf",
        "Please review the invoice and the purchase order.\n",
    )
    assert ambiguous_result.detected_type is DocumentType.UNKNOWN
    assert ambiguous_result.outcome is ExtractionOutcome.REVIEW_REQUIRED

    wrong, _, wrong_result = _understand(
        docs,
        understanding,
        "purchase-order.pdf",
        _purchase_order(),
        DocumentType.INVOICE,
    )
    assert wrong_result.detected_type is DocumentType.INVOICE
    assert wrong_result.outcome is ExtractionOutcome.VALIDATION_FAILED

    from app.db.models import DocumentExtractionResult

    extraction = db_session.scalar(
        select(DocumentExtractionResult).where(DocumentExtractionResult.document_id == missing.id)
    )
    assert extraction is not None
    task = reviews.create_review_task(document_id=missing.id, extraction_result_id=extraction.id)
    with pytest.raises(ReviewValidationError):
        reviews.approve(task.id, reviewer="qa")
    task.status = ReviewStatus.APPROVED.value
    db_session.commit()
    with pytest.raises(PromotionValidationError):
        promotion.promote(task.id)
    assert db_session.scalar(select(func.count()).select_from(Invoice)) == 0
    db_session.refresh(missing)
    assert missing.status == DocumentStatus.VALIDATION_FAILED.value
    assert dated.id and priced.id and lined.id and ambiguous.id and wrong.id
