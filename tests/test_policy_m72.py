"""M7.2 policy ingestion and deterministic chunking tests."""

from __future__ import annotations

import hashlib
from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PolicyChunk
from app.db.session import get_db
from app.domain.enums import PolicyVersionStatus
from app.main import app
from app.policy.chunking import chunk_sections
from app.policy.markdown import parse_markdown
from app.policy.pdf import PolicyPdfError, parse_pdf
from app.policy.schemas import ContentBlock, ParsedSection, ParsedSource
from app.services.policy_ingestion_service import PolicyIngestionService
from app.services.policy_service import (
    PolicyConflictError,
    PolicyService,
    PolicyValidationError,
    content_sha256,
)

client = TestClient(app)

SAMPLE_MD = """# Price Variance Policy

## 1. Purpose

This policy defines acceptable unit-price variance.

## 2. Definitions

### 2.1 Terms

- Unit price
- Tolerance band

### 2.2 Scope

Applies to all AP invoices linked to a purchase order.

## 3. Rules

Price variance must not exceed two percent.

Additional guidance for reviewers follows in the appendix paragraphs.
"""


@pytest.fixture
def api_client(db_session: Session) -> TestClient:
    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield client
    app.dependency_overrides.clear()


def _make_pdf(text: str) -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    y = 72
    for line in text.splitlines():
        if line.strip():
            page.insert_text((72, y), line[:100])
            y += 14
    data = doc.tobytes()
    doc.close()
    return data


def _seed_version(session: Session, *, label: str = "2026.1") -> tuple:
    svc = PolicyService(session)
    doc = svc.create_document(name=f"Policy-{uuid4().hex[:8]}")
    version = svc.create_version(
        doc.id,
        version_label=label,
        effective_from=date(2026, 1, 1),
        source_content="placeholder",
        status=PolicyVersionStatus.DRAFT,
    )
    return doc, version, svc


# --- Markdown -----------------------------------------------------------------


def test_markdown_headings_and_nested_sections() -> None:
    parsed = parse_markdown(SAMPLE_MD, source_filename="price.md")
    ids = [s.section_id for s in parsed.sections]
    assert "1" in ids
    assert "2.1" in ids
    assert "2.2" in ids
    terms = next(s for s in parsed.sections if s.section_id == "2.1")
    assert terms.section_title == "2.1 Terms"
    joined = terms.joined_text
    assert "Unit price" in joined
    assert "Tolerance band" in joined


def test_markdown_paragraphs_stay_with_section() -> None:
    parsed = parse_markdown(SAMPLE_MD)
    purpose = next(s for s in parsed.sections if s.section_id == "1")
    assert "acceptable unit-price variance" in purpose.joined_text


def test_large_section_split_deterministic() -> None:
    long_para = "word " * 800
    source = ParsedSource(
        sections=[
            ParsedSection(
                section_id="1",
                section_title="1 Big",
                level=2,
                blocks=[ContentBlock(text=long_para.strip())],
            )
        ],
        source_filename="big.md",
    )
    a = chunk_sections(source, max_chars=200)
    b = chunk_sections(source, max_chars=200)
    assert len(a) > 1
    assert [c.content for c in a] == [c.content for c in b]
    assert [c.content_hash for c in a] == [c.content_hash for c in b]
    assert [c.chunk_index for c in a] == list(range(len(a)))
    assert all(c.section_id == "1" for c in a)


def test_same_markdown_produces_identical_chunks() -> None:
    parsed = parse_markdown(SAMPLE_MD, source_filename="price.md")
    a = chunk_sections(parsed, max_chars=500)
    b = chunk_sections(parse_markdown(SAMPLE_MD, source_filename="price.md"), max_chars=500)
    assert [(c.chunk_index, c.content_hash, c.content) for c in a] == [
        (c.chunk_index, c.content_hash, c.content) for c in b
    ]


# --- PDF ----------------------------------------------------------------------


def test_pdf_extraction_and_page_provenance() -> None:
    text = (
        "1 Purpose\n"
        "This policy defines price variance.\n\n"
        "2 Rules\n"
        "Variance must stay within two percent.\n"
    )
    parsed = parse_pdf(_make_pdf(text), source_filename="policy.pdf")
    assert parsed.full_text.strip()
    assert any(s.page_number == 1 for s in parsed.sections)
    assert any(b.page_number == 1 for s in parsed.sections for b in s.blocks)


def test_empty_pdf_fails_clearly() -> None:
    import fitz

    doc = fitz.open()
    doc.new_page()
    data = doc.tobytes()
    doc.close()
    with pytest.raises(PolicyPdfError):
        parse_pdf(data, source_filename="blank.pdf")


# --- Ingestion ----------------------------------------------------------------


def test_source_hash_and_idempotent_ingest(db_session: Session) -> None:
    doc, version, _svc = _seed_version(db_session)
    data = SAMPLE_MD.encode("utf-8")
    expected = hashlib.sha256(data).hexdigest()
    ingestion = PolicyIngestionService(
        db_session, settings=Settings(policy_chunk_max_chars=500)
    )
    first = ingestion.ingest(doc.id, version.id, filename="price.md", data=data)
    assert first.status == "INGESTED"
    assert first.source_hash == expected
    assert first.chunks_created >= 1

    second = ingestion.ingest(doc.id, version.id, filename="price.md", data=data)
    assert second.status == "ALREADY_INGESTED"
    assert second.chunks_created == first.chunks_created

    chunks = list(
        db_session.scalars(
            select(PolicyChunk)
            .where(PolicyChunk.policy_version_id == version.id)
            .order_by(PolicyChunk.chunk_index)
        )
    )
    assert len(chunks) == first.chunks_created
    assert chunks[0].source_filename == "price.md"
    assert chunks[0].content_hash == content_sha256(chunks[0].content)


def test_different_source_after_ingest_conflicts(db_session: Session) -> None:
    doc, version, _svc = _seed_version(db_session)
    ingestion = PolicyIngestionService(db_session)
    ingestion.ingest(doc.id, version.id, filename="a.md", data=SAMPLE_MD.encode("utf-8"))
    with pytest.raises(PolicyConflictError):
        ingestion.ingest(
            doc.id,
            version.id,
            filename="b.md",
            data=b"# Other Policy\n\nDifferent body.\n",
        )


def test_unsupported_type_rejected(db_session: Session) -> None:
    doc, version, _svc = _seed_version(db_session)
    with pytest.raises(PolicyValidationError):
        PolicyIngestionService(db_session).ingest(
            doc.id, version.id, filename="policy.docx", data=b"x"
        )


def test_ingest_transaction_rollback(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    doc, version, _svc = _seed_version(db_session)
    ingestion = PolicyIngestionService(db_session)

    def boom(*_a, **_k):
        raise RuntimeError("simulated failure after parse")

    monkeypatch.setattr(
        "app.services.policy_ingestion_service.chunk_sections",
        boom,
    )
    with pytest.raises(RuntimeError):
        ingestion.ingest(doc.id, version.id, filename="price.md", data=SAMPLE_MD.encode("utf-8"))
    chunks = list(
        db_session.scalars(
            select(PolicyChunk).where(PolicyChunk.policy_version_id == version.id)
        )
    )
    assert chunks == []


def test_ingest_api(api_client: TestClient, db_session: Session) -> None:
    doc, version, _svc = _seed_version(db_session)
    response = api_client.post(
        f"/policies/{doc.id}/versions/{version.id}/ingest",
        files={"file": ("price.md", SAMPLE_MD.encode("utf-8"), "text/markdown")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "INGESTED"
    assert body["chunks_created"] >= 1
    assert body["source_hash"] == hashlib.sha256(SAMPLE_MD.encode("utf-8")).hexdigest()

    again = api_client.post(
        f"/policies/{doc.id}/versions/{version.id}/ingest",
        files={"file": ("price.md", SAMPLE_MD.encode("utf-8"), "text/markdown")},
    )
    assert again.status_code == 200
    assert again.json()["status"] == "ALREADY_INGESTED"

    bad = api_client.post(
        f"/policies/{doc.id}/versions/{version.id}/ingest",
        files={"file": ("x.docx", b"abc", "application/octet-stream")},
    )
    # Already ingested → conflict if different type after chunks exist, or 422 if empty version
    # Here version already has chunks from identical hash path above; docx is different bytes.
    assert bad.status_code in {409, 422}


def test_pdf_ingest_api(api_client: TestClient, db_session: Session) -> None:
    doc, version, _svc = _seed_version(db_session, label="pdf-1")
    pdf = _make_pdf("1 Purpose\nDefines variance.\n\n2 Rules\nKeep within 2%.\n")
    response = api_client.post(
        f"/policies/{doc.id}/versions/{version.id}/ingest",
        files={"file": ("policy.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "INGESTED"
    detail = api_client.get(f"/policies/{doc.id}/versions/{version.id}")
    assert detail.status_code == 200
    chunks = detail.json()["chunks"]
    assert chunks
    assert any(c.get("page_number") == 1 for c in chunks)
