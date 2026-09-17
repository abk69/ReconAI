"""Deterministic M4 document understanding tests."""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import DocumentExtractionResult, Invoice, PurchaseOrder
from app.db.session import get_db
from app.domain.enums import DocumentStatus, DocumentType, ExtractionOutcome
from app.extraction.classifier import classify_document
from app.extraction.normalizer import (
    normalize_date,
    normalize_money,
    normalize_percentage,
    normalize_quantity,
)
from app.extraction.pdf import PDFExtractor
from app.extraction.schemas import ExtractedDocument
from app.extraction.xlsx import XLSXExtractor
from app.main import app
from app.services.document_service import DocumentService
from app.services.document_understanding_service import DocumentUnderstandingService
from app.storage.local import LocalFileStorage

client = TestClient(app)


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


def _make_xlsx(headers: list[str], rows: list[list[object]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.append(headers)
    for row in rows:
        ws.append(row)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture
def understanding(
    db_session: Session, storage_root: Path
) -> tuple[DocumentService, DocumentUnderstandingService]:
    storage = LocalFileStorage(storage_root)
    return DocumentService(db_session, storage=storage), DocumentUnderstandingService(
        db_session, storage=storage
    )


def test_clean_invoice_pdf(understanding) -> None:
    docs, svc = understanding
    text = (
        "TAX INVOICE\n"
        "Invoice Number: INV-1001\n"
        "Vendor: Acme Supplies\n"
        "Invoice Date: 2026-09-15\n"
        "PO Number: PO-1001\n"
        "Widget A 10 500.00\n"
    )
    row, _ = docs.upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    result = svc.understand(row.id)
    assert result.detected_type is DocumentType.INVOICE
    assert result.candidate is not None
    assert result.candidate["invoice_number"] == "INV-1001"
    assert result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION
    assert result.document_status == DocumentStatus.READY_FOR_RECONCILIATION.value


def test_invoice_with_multiple_lines(understanding) -> None:
    docs, svc = understanding
    text = (
        "Invoice Number: INV-2002\n"
        "Vendor: Beta Corp\n"
        "Invoice Date: 2026-09-16\n"
        "Item One 5 100.00\n"
        "Item Two 2 250.50\n"
    )
    row, _ = docs.upload(
        filename="multi-invoice.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    result = svc.understand(row.id)
    assert result.candidate is not None
    assert len(result.candidate["lines"]) >= 2


def test_clean_po_pdf(understanding) -> None:
    docs, svc = understanding
    text = (
        "Purchase Order\n"
        "PO Number: PO-3003\n"
        "Vendor: Gamma Ltd\n"
        "PO Date: 2026-09-10\n"
        "Bolt Set 50 12.00\n"
    )
    row, _ = docs.upload(
        filename="purchase_order.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.PO,
    )
    result = svc.understand(row.id)
    assert result.detected_type is DocumentType.PO
    assert result.candidate is not None
    assert result.candidate["po_number"] == "PO-3003"
    assert result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION


def test_partial_grn(understanding) -> None:
    docs, svc = understanding
    text = (
        "Goods Receipt Note\n"
        "GRN Number: GRN-4004\n"
        "PO Number: PO-3003\n"
        "Receipt Date: 2026-09-12\n"
        "Received Quantity: 40\n"
    )
    row, _ = docs.upload(
        filename="grn.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.GRN,
    )
    result = svc.understand(row.id)
    assert result.detected_type is DocumentType.GRN
    assert result.candidate is not None
    assert result.candidate["grn_number"] == "GRN-4004"
    assert result.outcome is ExtractionOutcome.READY_FOR_RECONCILIATION


def test_xlsx_invoice(understanding) -> None:
    docs, svc = understanding
    data = _make_xlsx(
        ["Description", "Qty", "Unit Price", "Tax"],
        [["Widget", 10, "500.00", "18%"]],
    )
    # Embed labels in a second sheet via filename + extra header text sheet
    from openpyxl import Workbook

    wb = Workbook()
    meta = wb.active
    assert meta is not None
    meta.title = "Header"
    meta["A1"] = "Invoice Number"
    meta["B1"] = "INV-XLSX-1"
    meta["A2"] = "Vendor"
    meta["B2"] = "Sheet Vendor"
    meta["A3"] = "Invoice Date"
    meta["B3"] = "2026-09-15"
    lines = wb.create_sheet("Lines")
    lines.append(["Description", "Qty", "Unit Price", "Tax"])
    lines.append(["Widget", 10, "500.00", "18%"])
    buf = BytesIO()
    wb.save(buf)
    data = buf.getvalue()

    row, _ = docs.upload(
        filename="invoice.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=data,
        document_type=DocumentType.INVOICE,
    )
    result = svc.understand(row.id)
    assert result.detected_type is DocumentType.INVOICE
    assert result.candidate is not None
    assert result.candidate["invoice_number"] == "INV-XLSX-1"
    assert len(result.candidate["lines"]) >= 1


def test_xlsx_po(understanding) -> None:
    docs, svc = understanding
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws["A1"] = "PO Number: PO-XLSX-9"
    ws["A2"] = "Vendor: Sheet PO Vendor"
    ws["A3"] = "PO Date: 2026-09-10"
    lines = wb.create_sheet("Lines")
    lines.append(["Description", "Quantity", "Unit Price"])
    lines.append(["Nut", 20, "2.50"])
    buf = BytesIO()
    wb.save(buf)

    row, _ = docs.upload(
        filename="purchase_order.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=buf.getvalue(),
        document_type=DocumentType.PO,
    )
    result = svc.understand(row.id)
    assert result.detected_type is DocumentType.PO
    assert result.candidate is not None
    assert result.candidate["po_number"] == "PO-XLSX-9"


def test_image_ocr_path_graceful(understanding) -> None:
    docs, svc = understanding
    # Minimal PNG header-ish bytes may fail OCR / open — still must not crash.
    row, _ = docs.upload(
        filename="scan.png",
        content_type="image/png",
        data=b"\x89PNG\r\n\x1a\n" + b"\x00" * 64,
    )
    result = svc.understand(row.id)
    assert result.outcome in {
        ExtractionOutcome.REVIEW_REQUIRED,
        ExtractionOutcome.VALIDATION_FAILED,
        ExtractionOutcome.EXTRACTION_FAILED,
    }
    assert result.document_status in {
        DocumentStatus.REVIEW_REQUIRED.value,
        DocumentStatus.VALIDATION_FAILED.value,
        DocumentStatus.EXTRACTION_FAILED.value,
    }


def test_unknown_document(understanding) -> None:
    docs, svc = understanding
    row, _ = docs.upload(
        filename="notes.pdf",
        content_type="application/pdf",
        data=_make_pdf("Hello world random memo"),
    )
    result = svc.understand(row.id)
    assert result.detected_type is DocumentType.UNKNOWN
    assert result.outcome is ExtractionOutcome.REVIEW_REQUIRED


def test_missing_invoice_number(understanding) -> None:
    docs, svc = understanding
    text = "Invoice\nVendor: Acme\nInvoice Date: 2026-09-15\nWidget 1 10.00\n"
    row, _ = docs.upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    result = svc.understand(row.id)
    assert result.outcome is ExtractionOutcome.VALIDATION_FAILED
    codes = {i.code for i in result.validation.issues}
    assert "MISSING_INVOICE_NUMBER" in codes


def test_invalid_quantity_normalization() -> None:
    assert normalize_quantity("abc") is None
    assert normalize_quantity("12.5") == Decimal("12.5")


def test_invalid_price_normalization() -> None:
    assert normalize_money("not-a-price") is None
    assert normalize_money("₹1,250.50") == Decimal("1250.50")


def test_currency_formatting() -> None:
    assert normalize_money("$1,000.00") == Decimal("1000.00")
    assert normalize_money("€ 99.99") == Decimal("99.99")


def test_percentage_formatting() -> None:
    assert normalize_percentage("18%") == Decimal("0.18")
    assert normalize_percentage("18.0 %") == Decimal("0.18")
    assert normalize_percentage("0.18") == Decimal("0.18")


def test_date_normalization() -> None:
    assert normalize_date("2026-09-15").isoformat() == "2026-09-15"  # type: ignore[union-attr]
    assert normalize_date("15/09/2026").isoformat() == "2026-09-15"  # type: ignore[union-attr]
    assert normalize_date("not-a-date") is None


def test_provenance_preservation(understanding) -> None:
    docs, svc = understanding
    text = (
        "Invoice Number: INV-PROV-1\n"
        "Vendor: Prov Vendor\n"
        "Invoice Date: 2026-09-15\n"
        "Widget 3 99.00\n"
    )
    row, _ = docs.upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    result = svc.understand(row.id)
    assert result.evidence
    assert any(e.field_name == "invoice_number" for e in result.evidence)
    assert any(e.source_text for e in result.evidence)


def test_validation_failure_status(understanding) -> None:
    docs, svc = understanding
    row, _ = docs.upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        data=_make_pdf("Invoice Number: INV-X\nVendor: V\n"),
        document_type=DocumentType.INVOICE,
    )
    result = svc.understand(row.id)
    assert result.document_status == DocumentStatus.VALIDATION_FAILED.value


def test_review_required_unknown(understanding) -> None:
    docs, svc = understanding
    row, _ = docs.upload(
        filename="mystery.pdf",
        content_type="application/pdf",
        data=_make_pdf("unclear content"),
    )
    result = svc.understand(row.id)
    assert result.outcome is ExtractionOutcome.REVIEW_REQUIRED


def test_pdf_extractor_page_numbers() -> None:
    data = _make_pdf("Invoice Number: INV-P1\nPage content")
    extracted = PDFExtractor().extract(
        document_id=uuid4(),
        data=data,
        filename="a.pdf",
        mime_type="application/pdf",
    )
    assert extracted.pages
    assert extracted.text_blocks[0].page == 1


def test_xlsx_extractor_cell_provenance() -> None:
    data = _make_xlsx(["A", "B"], [["1", "2"]])
    extracted = XLSXExtractor().extract(
        document_id=uuid4(),
        data=data,
        filename="a.xlsx",
        mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    assert extracted.tables
    assert extracted.tables[0].cells
    assert extracted.tables[0].cells[0].cell_ref is not None


def test_classifier_filename_and_labels() -> None:
    extracted = ExtractedDocument(
        document_id=uuid4(),
        full_text="Invoice Number: INV-1\nVendor: X",
        extractor_name="test",
        metadata={"labelled_fields": {"invoice_number": "INV-1"}, "filename": "x.pdf"},
    )
    assert classify_document(extracted) is DocumentType.INVOICE


def test_extraction_idempotency(understanding, db_session: Session) -> None:
    docs, svc = understanding
    text = (
        "Invoice Number: INV-IDEMP\nVendor: Idem Vendor\nInvoice Date: 2026-09-15\nWidget 1 10.00\n"
    )
    row, _ = docs.upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    first = svc.understand(row.id)
    second = svc.understand(row.id)
    assert first.outcome == second.outcome
    count = len(
        list(
            db_session.scalars(
                select(DocumentExtractionResult).where(
                    DocumentExtractionResult.document_id == row.id
                )
            )
        )
    )
    assert count == 1


def test_does_not_write_authoritative_financial_records(understanding, db_session: Session) -> None:
    docs, svc = understanding
    text = (
        "Invoice Number: INV-NOWRITE\n"
        "Vendor: No Write Vendor\n"
        "Invoice Date: 2026-09-15\n"
        "Widget 1 10.00\n"
    )
    row, _ = docs.upload(
        filename="invoice.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.INVOICE,
    )
    svc.understand(row.id)
    assert db_session.scalars(select(Invoice)).first() is None
    assert db_session.scalars(select(PurchaseOrder)).first() is None
    assert (
        db_session.scalars(
            select(DocumentExtractionResult).where(DocumentExtractionResult.document_id == row.id)
        ).first()
        is not None
    )


def test_status_transitions(understanding, db_session: Session) -> None:
    docs, svc = understanding
    text = "PO Number: PO-STATUS\nVendor: Status Vendor\nPO Date: 2026-09-10\nItem 1 5.00\n"
    row, _ = docs.upload(
        filename="purchase_order.pdf",
        content_type="application/pdf",
        data=_make_pdf(text),
        document_type=DocumentType.PO,
    )
    assert row.status == DocumentStatus.VALIDATED.value
    result = svc.understand(row.id)
    assert result.document_status == DocumentStatus.READY_FOR_RECONCILIATION.value


def test_api_understand_and_get(db_session: Session, storage_root: Path) -> None:
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        upload = client.post(
            "/documents",
            files={
                "file": (
                    "invoice.pdf",
                    _make_pdf(
                        "Invoice Number: INV-API\n"
                        "Vendor: API Vendor\n"
                        "Invoice Date: 2026-09-15\n"
                        "Widget 1 10.00\n"
                    ),
                    "application/pdf",
                )
            },
            data={"document_type": "INVOICE"},
        )
        assert upload.status_code == 201
        doc_id = upload.json()["id"]
        understand = client.post(f"/documents/{doc_id}/understand")
        assert understand.status_code == 200
        body = understand.json()
        assert body["outcome"] in {
            "READY_FOR_RECONCILIATION",
            "VALIDATION_FAILED",
            "REVIEW_REQUIRED",
        }
        assert "storage_path" not in body
        fetched = client.get(f"/documents/{doc_id}/understanding")
        assert fetched.status_code == 200
        assert fetched.json()["document_id"] == doc_id
    finally:
        app.dependency_overrides.clear()
