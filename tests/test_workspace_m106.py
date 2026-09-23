"""M10.6 read-only document intelligence queries."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentExtractionResult, ReviewTask
from app.db.session import get_db
from app.main import app


def _client(db_session: Session) -> TestClient:
    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    return TestClient(app)


def _document(name: str, *, status: str = "VALIDATED") -> Document:
    return Document(
        original_filename=name,
        stored_filename=f"{name}.bin",
        document_type="INVOICE",
        mime_type="application/pdf",
        file_extension=".pdf",
        file_size=12,
        sha256=name.encode().hex().ljust(64, "a")[:64],
        storage_path="storage/secret-path",
        status=status,
    )


def test_document_list_facts_filters_and_raw_extraction(db_session: Session) -> None:
    plain = _document("plain.pdf")
    reviewed = _document("reviewed.pdf", status="REVIEW_REQUIRED")
    db_session.add_all([plain, reviewed])
    db_session.flush()
    extraction = DocumentExtractionResult(
        document_id=reviewed.id,
        detected_type="INVOICE",
        outcome="REVIEW_REQUIRED",
        raw_extraction={
            "full_text": "Invoice INV-1",
            "storage_path": "C:/secret/file.pdf",
            "metadata": {"api_key": "should-not-leak", "pages": 1},
        },
        candidate={"invoice_number": "INV-1"},
        validation={"is_valid": False, "requires_review": True, "issues": []},
        evidence=[],
    )
    db_session.add(extraction)
    db_session.flush()
    db_session.add(
        ReviewTask(
            document_id=reviewed.id,
            extraction_result_id=extraction.id,
            status="PENDING",
            priority="MEDIUM",
            reason="Identifier needs a person",
        )
    )
    db_session.commit()

    client = _client(db_session)
    try:
        listed = client.get("/documents", params={"limit": 25})
        assert listed.status_code == 200
        by_name = {item["original_filename"]: item for item in listed.json()["items"]}
        assert by_name["plain.pdf"]["extraction_outcome"] is None
        assert by_name["plain.pdf"]["review_status"] is None
        assert by_name["reviewed.pdf"]["extraction_outcome"] == "REVIEW_REQUIRED"
        assert by_name["reviewed.pdf"]["detected_type"] == "INVOICE"
        assert by_name["reviewed.pdf"]["review_status"] == "PENDING"
        assert "storage/secret-path" in listed.text

        filtered = client.get("/documents", params={"extraction_outcome": "REVIEW_REQUIRED"})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["items"][0]["original_filename"] == "reviewed.pdf"

        pending = client.get("/documents", params={"review_status": "PENDING"})
        assert pending.json()["total"] == 1

        none = client.get("/documents", params={"extraction_outcome": "VALIDATION_FAILED"})
        assert none.status_code == 200
        assert none.json()["total"] == 0

        tasks = client.get("/review/tasks", params={"document_id": str(reviewed.id)})
        assert tasks.status_code == 200
        assert tasks.json()["total"] == 1
        assert tasks.json()["items"][0]["document_id"] == str(reviewed.id)
        other = client.get("/review/tasks", params={"document_id": str(plain.id)})
        assert other.json()["total"] == 0

        raw = client.get(f"/documents/{reviewed.id}/raw-extraction")
        assert raw.status_code == 200
        body = raw.json()["raw_extraction"]
        assert body["full_text"] == "Invoice INV-1"
        assert "storage_path" not in body
        assert "api_key" not in body["metadata"]
        assert body["metadata"]["pages"] == 1
        missing = client.get(f"/documents/{plain.id}/raw-extraction")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
