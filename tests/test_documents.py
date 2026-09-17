"""Document intake and local storage tests (no OCR / AI)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document
from app.db.session import get_db
from app.domain.enums import DocumentStatus, DocumentType
from app.main import app
from app.services.document_service import (
    DocumentAssociationError,
    DocumentService,
    DocumentValidationError,
    compute_sha256,
    sanitize_original_filename,
    validate_upload,
)
from app.services.procurement_service import ProcurementService
from app.storage.base import StorageError
from app.storage.local import LocalFileStorage

client = TestClient(app)

PDF_BYTES = b"%PDF-1.4 minimal test content"
JPEG_BYTES = b"\xff\xd8\xff jpeg-test-bytes"
PNG_BYTES = b"\x89PNG\r\n\x1a\n png-test-bytes"
XLSX_BYTES = b"PK\x03\x04 xlsx-zip-test-bytes"


@pytest.fixture
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "documents"
    monkeypatch.setenv("STORAGE_ROOT", str(root))
    monkeypatch.setenv("MAX_UPLOAD_BYTES", str(10 * 1024 * 1024))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture
def doc_service(db_session: Session, storage_root: Path) -> DocumentService:
    return DocumentService(db_session, storage=LocalFileStorage(storage_root))


def test_valid_pdf_upload(doc_service: DocumentService, storage_root: Path) -> None:
    row, dup = doc_service.upload(
        filename="po.pdf",
        content_type="application/pdf",
        data=PDF_BYTES,
        document_type=DocumentType.PO,
    )
    assert not dup
    assert row.status == DocumentStatus.VALIDATED.value
    assert row.file_extension == ".pdf"
    assert (storage_root / row.stored_filename).exists()


def test_valid_jpeg_upload(doc_service: DocumentService) -> None:
    row, _ = doc_service.upload(
        filename="scan.jpg",
        content_type="image/jpeg",
        data=JPEG_BYTES,
    )
    assert row.mime_type == "image/jpeg"
    assert row.file_extension == ".jpg"


def test_valid_png_upload(doc_service: DocumentService) -> None:
    row, _ = doc_service.upload(
        filename="scan.png",
        content_type="image/png",
        data=PNG_BYTES,
    )
    assert row.file_extension == ".png"


def test_valid_xlsx_upload(doc_service: DocumentService) -> None:
    row, _ = doc_service.upload(
        filename="lines.xlsx",
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=XLSX_BYTES,
    )
    assert row.file_extension == ".xlsx"


def test_unsupported_extension() -> None:
    with pytest.raises(DocumentValidationError):
        validate_upload(
            original_filename="virus.exe",
            content_type="application/octet-stream",
            data=b"x",
            max_upload_bytes=1024,
        )


def test_unsupported_mime_type() -> None:
    with pytest.raises(DocumentValidationError):
        validate_upload(
            original_filename="po.pdf",
            content_type="text/plain",
            data=PDF_BYTES,
            max_upload_bytes=1024,
        )


def test_file_too_large() -> None:
    with pytest.raises(DocumentValidationError):
        validate_upload(
            original_filename="po.pdf",
            content_type="application/pdf",
            data=b"a" * 100,
            max_upload_bytes=50,
        )


def test_safe_generated_storage_filename(doc_service: DocumentService) -> None:
    row, _ = doc_service.upload(
        filename="../../evil.pdf",
        content_type="application/pdf",
        data=PDF_BYTES,
    )
    assert row.stored_filename == f"{row.id}.pdf"
    assert ".." not in row.stored_filename
    assert "/" not in row.stored_filename


def test_original_filename_preserved_as_metadata_only(doc_service: DocumentService) -> None:
    row, _ = doc_service.upload(
        filename="reports/Q1 Invoice.PDF",
        content_type="application/pdf",
        data=PDF_BYTES + b"-meta",
    )
    assert row.original_filename == "Q1 Invoice.PDF"
    assert row.stored_filename.startswith(str(row.id))


def test_sha256_calculation(doc_service: DocumentService) -> None:
    data = PDF_BYTES + b"-hash"
    row, _ = doc_service.upload(
        filename="a.pdf",
        content_type="application/pdf",
        data=data,
    )
    assert row.sha256 == compute_sha256(data)


def test_exact_duplicate_detection(doc_service: DocumentService, storage_root: Path) -> None:
    data = PDF_BYTES + b"-dup"
    first, dup1 = doc_service.upload(
        filename="a.pdf",
        content_type="application/pdf",
        data=data,
    )
    second, dup2 = doc_service.upload(
        filename="b.pdf",
        content_type="application/pdf",
        data=data,
    )
    assert not dup1
    assert dup2
    assert first.id == second.id
    assert len(list(storage_root.glob("*.pdf"))) == 1


def test_missing_storage_directory_handling(tmp_path: Path, db_session: Session) -> None:
    root = tmp_path / "nested" / "docs"
    assert not root.exists()
    service = DocumentService(db_session, storage=LocalFileStorage(root))
    row, _ = service.upload(
        filename="a.pdf",
        content_type="application/pdf",
        data=PDF_BYTES + b"-mkdir",
    )
    assert root.exists()
    assert (root / row.stored_filename).exists()


def test_path_traversal_attempt() -> None:
    assert sanitize_original_filename("../../etc/passwd.pdf") == "passwd.pdf"
    storage = LocalFileStorage(Path("/tmp/reconai-safe-root"))
    with pytest.raises(StorageError):
        storage._resolve_safe_path("../escape.pdf")


def test_document_metadata_persistence(doc_service: DocumentService, db_session: Session) -> None:
    row, _ = doc_service.upload(
        filename="persist.pdf",
        content_type="application/pdf",
        data=PDF_BYTES + b"-persist",
        document_type=DocumentType.INVOICE,
    )
    loaded = db_session.get(Document, row.id)
    assert loaded is not None
    assert loaded.document_type == DocumentType.INVOICE.value
    assert loaded.status == DocumentStatus.VALIDATED.value


def test_document_filters(doc_service: DocumentService) -> None:
    doc_service.upload(
        filename="po.pdf",
        content_type="application/pdf",
        data=PDF_BYTES + b"-f1",
        document_type=DocumentType.PO,
    )
    doc_service.upload(
        filename="inv.pdf",
        content_type="application/pdf",
        data=PDF_BYTES + b"-f2",
        document_type=DocumentType.INVOICE,
    )
    only_po = doc_service.list(document_type=DocumentType.PO)
    assert all(d.document_type == DocumentType.PO.value for d in only_po)
    assert len(only_po) >= 1


def test_document_association_with_po(doc_service: DocumentService, db_session: Session) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V1", tax_id=f"T-{uuid4().hex[:6]}")
    po = ProcurementService(db_session).create_purchase_order(
        po_number=f"PO-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        order_date=date(2026, 9, 1),
        lines=[
            {
                "line_number": 1,
                "quantity": Decimal("1"),
                "unit_price": Decimal("10"),
                "tax_rate": Decimal("0"),
            }
        ],
    )
    row, _ = doc_service.upload(
        filename="po.pdf",
        content_type="application/pdf",
        data=PDF_BYTES + b"-assoc-po",
        document_type=DocumentType.PO,
        purchase_order_id=po.id,
        vendor_id=vendor.id,
    )
    assert row.purchase_order_id == po.id


def test_document_association_with_invoice(
    doc_service: DocumentService, db_session: Session
) -> None:
    vendor = ProcurementService(db_session).create_vendor(name="V2", tax_id=f"T-{uuid4().hex[:6]}")
    invoice = ProcurementService(db_session).create_invoice(
        invoice_number=f"INV-{uuid4().hex[:6]}",
        vendor_id=vendor.id,
        invoice_date=date(2026, 9, 2),
        total_amount=Decimal("10"),
    )
    row, _ = doc_service.upload(
        filename="inv.pdf",
        content_type="application/pdf",
        data=PDF_BYTES + b"-assoc-inv",
        document_type=DocumentType.INVOICE,
        invoice_id=invoice.id,
    )
    assert row.invoice_id == invoice.id


def test_invalid_foreign_key_association(doc_service: DocumentService) -> None:
    with pytest.raises(DocumentAssociationError):
        doc_service.upload(
            filename="po.pdf",
            content_type="application/pdf",
            data=PDF_BYTES + b"-bad-fk",
            purchase_order_id=uuid4(),
        )


def test_document_lifecycle_status(doc_service: DocumentService) -> None:
    row, _ = doc_service.upload(
        filename="life.pdf",
        content_type="application/pdf",
        data=PDF_BYTES + b"-life",
    )
    assert row.status == DocumentStatus.VALIDATED.value


def test_storage_failure_handling(db_session: Session, storage_root: Path) -> None:
    class FailingStorage(LocalFileStorage):
        def save(self, *, document_id, extension, data):  # type: ignore[no-untyped-def]
            raise StorageError("disk full")

    service = DocumentService(db_session, storage=FailingStorage(storage_root))
    with pytest.raises(Exception) as exc_info:
        service.upload(
            filename="x.pdf",
            content_type="application/pdf",
            data=PDF_BYTES + b"-fail",
        )
    assert "disk full" in str(exc_info.value)


def test_api_document_upload_and_get(db_session: Session, storage_root: Path) -> None:
    def _override():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    try:
        response = client.post(
            "/documents",
            files={"file": ("api.pdf", PDF_BYTES + b"-api", "application/pdf")},
            data={"document_type": "PO"},
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "VALIDATED"
        assert body["is_duplicate"] is False
        get_resp = client.get(f"/documents/{body['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["sha256"] == body["sha256"]
    finally:
        app.dependency_overrides.clear()
