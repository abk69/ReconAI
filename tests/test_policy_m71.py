"""M7.1 policy knowledge-base foundation tests (no embeddings/RAG)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.enums import PolicyVersionStatus
from app.main import app
from app.services.policy_service import (
    PolicyConflictError,
    PolicyNotFoundError,
    PolicyService,
    PolicyValidationError,
    content_sha256,
)

client = TestClient(app)


@pytest.fixture
def api_client(db_session: Session) -> TestClient:
    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield client
    app.dependency_overrides.clear()


def test_policy_document_creation(db_session: Session) -> None:
    svc = PolicyService(db_session)
    doc = svc.create_document(name="Price Variance Policy", description="PV rules")
    assert doc.id is not None
    assert doc.name == "Price Variance Policy"
    loaded = svc.get_document(doc.id)
    assert loaded.description == "PV rules"


def test_duplicate_policy_document_name_rejected(db_session: Session) -> None:
    svc = PolicyService(db_session)
    svc.create_document(name="Tax Policy")
    with pytest.raises(PolicyConflictError):
        svc.create_document(name="Tax Policy")


def test_multiple_versions_for_one_document(db_session: Session) -> None:
    svc = PolicyService(db_session)
    doc = svc.create_document(name="Quantity Tolerance Policy")
    v1 = svc.create_version(
        doc.id,
        version_label="2025.1",
        effective_from=date(2025, 1, 1),
        source_content="v1 body",
        status=PolicyVersionStatus.RETIRED,
    )
    v2 = svc.create_version(
        doc.id,
        version_label="2026.1",
        effective_from=date(2026, 1, 1),
        effective_to=date(2026, 12, 31),
        source_content="v2 body",
        status=PolicyVersionStatus.ACTIVE,
        source_filename="qty-tolerance-2026.md",
        source_reference="sharepoint://policies/qty-2026",
    )
    versions = svc.list_versions(doc.id)
    assert len(versions) == 2
    assert {v.version_label for v in versions} == {"2025.1", "2026.1"}
    assert v1.content_hash == content_sha256("v1 body")
    assert v2.effective_from == date(2026, 1, 1)
    assert v2.effective_to == date(2026, 12, 31)
    assert v2.source_filename == "qty-tolerance-2026.md"
    assert v2.source_reference == "sharepoint://policies/qty-2026"


def test_version_label_uniqueness(db_session: Session) -> None:
    svc = PolicyService(db_session)
    doc = svc.create_document(name="Vendor Onboarding Policy")
    svc.create_version(
        doc.id,
        version_label="2026.1",
        effective_from=date(2026, 1, 1),
        source_content="same label",
    )
    with pytest.raises(PolicyConflictError):
        svc.create_version(
            doc.id,
            version_label="2026.1",
            effective_from=date(2026, 6, 1),
            source_content="duplicate label",
        )


def test_effective_date_validation(db_session: Session) -> None:
    svc = PolicyService(db_session)
    doc = svc.create_document(name="Date Guard Policy")
    with pytest.raises(PolicyValidationError):
        svc.create_version(
            doc.id,
            version_label="bad",
            effective_from=date(2026, 6, 1),
            effective_to=date(2026, 1, 1),
            source_content="x",
        )


def test_chunks_ordering_and_provenance(db_session: Session) -> None:
    svc = PolicyService(db_session)
    doc = svc.create_document(name="Invoice Matching Policy")
    version = svc.create_version(
        doc.id,
        version_label="2026.1",
        title="Invoice Matching Policy v2026.1",
        effective_from=date(2026, 3, 1),
        source_content="full policy text",
        source_filename="invoice-matching.pdf",
    )
    chunks = svc.add_chunks(
        doc.id,
        version.id,
        [
            {
                "chunk_index": 1,
                "section_id": "2.1",
                "section_title": "Price variance",
                "content": "Unit price may vary by at most 2%.",
                "source_filename": "invoice-matching.pdf",
                "page_number": 3,
            },
            {
                "chunk_index": 0,
                "section_id": "1.0",
                "section_title": "Scope",
                "content": "Applies to all AP invoices.",
                "source_filename": "invoice-matching.pdf",
                "page_number": 1,
            },
        ],
    )
    assert [c.chunk_index for c in chunks] == [0, 1]
    assert chunks[0].section_id == "1.0"
    assert chunks[1].page_number == 3
    assert chunks[1].content_hash == content_sha256("Unit price may vary by at most 2%.")

    detail = svc.get_version(doc.id, version.id)
    assert len(detail.chunks) == 2
    assert detail.chunks[0].chunk_index == 0
    assert detail.source_filename == "invoice-matching.pdf"


def test_duplicate_chunk_index_rejected(db_session: Session) -> None:
    svc = PolicyService(db_session)
    doc = svc.create_document(name="Duplicate Chunk Policy")
    version = svc.create_version(
        doc.id,
        version_label="1",
        effective_from=date(2026, 1, 1),
        source_content="body",
    )
    svc.add_chunks(
        doc.id,
        version.id,
        [{"chunk_index": 0, "content": "first"}],
    )
    with pytest.raises(PolicyConflictError):
        svc.add_chunks(
            doc.id,
            version.id,
            [{"chunk_index": 0, "content": "duplicate index"}],
        )


def test_foreign_key_invalid_references(db_session: Session) -> None:
    svc = PolicyService(db_session)
    missing = uuid4()
    with pytest.raises(PolicyNotFoundError):
        svc.get_document(missing)
    with pytest.raises(PolicyNotFoundError):
        svc.create_version(
            missing,
            version_label="1",
            effective_from=date(2026, 1, 1),
            source_content="x",
        )
    doc = svc.create_document(name="FK Policy")
    with pytest.raises(PolicyNotFoundError):
        svc.get_version(doc.id, uuid4())


def test_policy_api_endpoints(api_client: TestClient) -> None:
    created = api_client.post(
        "/policies",
        json={"name": "API Price Policy", "description": "via API"},
    )
    assert created.status_code == 201
    policy_id = created.json()["id"]

    listed = api_client.get("/policies")
    assert listed.status_code == 200
    assert listed.json()["count"] >= 1

    got = api_client.get(f"/policies/{policy_id}")
    assert got.status_code == 200
    assert got.json()["name"] == "API Price Policy"

    version = api_client.post(
        f"/policies/{policy_id}/versions",
        json={
            "version_label": "2026.1",
            "title": "API Price Policy v2026.1",
            "status": "ACTIVE",
            "effective_from": "2026-01-01",
            "source_content": "policy body for hash",
            "source_filename": "api-price.md",
        },
    )
    assert version.status_code == 201
    version_id = version.json()["id"]
    assert version.json()["content_hash"] == content_sha256("policy body for hash")

    versions = api_client.get(f"/policies/{policy_id}/versions")
    assert versions.status_code == 200
    assert versions.json()["count"] == 1

    chunks = api_client.post(
        f"/policies/{policy_id}/versions/{version_id}/chunks",
        json={
            "chunks": [
                {
                    "chunk_index": 0,
                    "section_id": "A",
                    "section_title": "Intro",
                    "content": "Cite this text.",
                    "page_number": 1,
                    "source_filename": "api-price.md",
                }
            ]
        },
    )
    assert chunks.status_code == 201
    assert chunks.json()["count"] == 1
    assert chunks.json()["items"][0]["section_id"] == "A"

    detail = api_client.get(f"/policies/{policy_id}/versions/{version_id}")
    assert detail.status_code == 200
    assert detail.json()["chunks"][0]["content"] == "Cite this text."

    listed_chunks = api_client.get(f"/policies/{policy_id}/versions/{version_id}/chunks")
    assert listed_chunks.status_code == 200
    assert listed_chunks.json()["count"] == 1


def test_policy_api_invalid_references(api_client: TestClient) -> None:
    missing = uuid4()
    assert api_client.get(f"/policies/{missing}").status_code == 404
    bad_version = api_client.post(
        f"/policies/{missing}/versions",
        json={
            "version_label": "1",
            "effective_from": "2026-01-01",
            "source_content": "x",
        },
    )
    assert bad_version.status_code == 404
