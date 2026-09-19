"""M7.3 policy embeddings + vector retrieval tests (offline; fake provider)."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PolicyChunk
from app.db.session import get_db
from app.domain.enums import PolicyVersionStatus
from app.embeddings.base import EmbeddingProvider, EmbeddingProviderError
from app.embeddings.constants import DEFAULT_EMBEDDING_DIMENSION
from app.embeddings.fake import FakeEmbeddingProvider
from app.main import app
from app.services.policy_embedding_service import PolicyEmbeddingService
from app.services.policy_retrieval_service import PolicyRetrievalService
from app.services.policy_service import PolicyService, content_sha256

client = TestClient(app)

DIM = DEFAULT_EMBEDDING_DIMENSION


@pytest.fixture
def api_client(db_session: Session) -> TestClient:
    def _override() -> Session:
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def fake_provider() -> FakeEmbeddingProvider:
    return FakeEmbeddingProvider(model="fake-embedding", dimension=DIM)


def _seed_chunks(session: Session, *, n: int = 3) -> tuple:
    svc = PolicyService(session)
    doc = svc.create_document(name=f"Embed-Policy-{uuid4().hex[:8]}")
    version = svc.create_version(
        doc.id,
        version_label="2026.1",
        effective_from=date(2026, 1, 1),
        source_content="seed",
        status=PolicyVersionStatus.DRAFT,
    )
    payloads = []
    texts = [
        "Price variance must not exceed two percent of the purchase order unit price.",
        "Quantity tolerance allows a five percent over-delivery on goods receipts.",
        "Tax rate discrepancies require human review before promotion to financial truth.",
    ]
    for i in range(n):
        text = texts[i % len(texts)]
        payloads.append(
            {
                "chunk_index": i,
                "section_id": str(i + 1),
                "section_title": f"Section {i + 1}",
                "content": text,
                "content_hash": content_sha256(text),
                "source_filename": "policy.md",
                "page_number": 1,
            }
        )
    chunks = svc.add_chunks(doc.id, version.id, payloads)
    return doc, version, chunks, svc


class _FailingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        self.calls = 0

    @property
    def model(self) -> str:
        return "failing"

    @property
    def dimension(self) -> int:
        return DIM

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        raise EmbeddingProviderError("simulated provider failure", code="PROVIDER_ERROR")


def test_migration_adds_embedding_columns(migrated_engine) -> None:
    cols = {c["name"] for c in inspect(migrated_engine).get_columns("policy_chunks")}
    assert "embedding" in cols
    assert "embedding_model" in cols
    assert "embedding_content_hash" in cols
    assert "embedded_at" in cols


def test_chunk_stores_embedding_vector(
    db_session: Session, fake_provider: FakeEmbeddingProvider
) -> None:
    doc, version, chunks, _ = _seed_chunks(db_session, n=1)
    svc = PolicyEmbeddingService(db_session, provider=fake_provider)
    summary = svc.embed_version(doc.id, version.id)
    assert summary.status == "EMBEDDED"
    assert summary.chunks_embedded == 1

    chunk = db_session.get(PolicyChunk, chunks[0].id)
    assert chunk is not None
    assert chunk.embedding is not None
    assert len(chunk.embedding) == DIM
    assert chunk.embedding_model == fake_provider.model
    assert chunk.embedding_content_hash == chunk.content_hash
    assert chunk.embedded_at is not None


def test_dimension_mismatch_rejected(db_session: Session) -> None:
    class BadDim(FakeEmbeddingProvider):
        def embed_texts(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] * 16 for _ in texts]

    doc, version, _, _ = _seed_chunks(db_session, n=1)
    svc = PolicyEmbeddingService(db_session, provider=BadDim(dimension=DIM))
    with pytest.raises(EmbeddingProviderError) as exc:
        svc.embed_version(doc.id, version.id)
    assert exc.value.code == "DIMENSION_MISMATCH"
    chunk = db_session.scalars(
        select(PolicyChunk).where(PolicyChunk.policy_version_id == version.id)
    ).first()
    assert chunk is not None
    assert chunk.embedding is None


def test_missing_and_skip_current(
    db_session: Session, fake_provider: FakeEmbeddingProvider
) -> None:
    doc, version, _, _ = _seed_chunks(db_session, n=2)
    svc = PolicyEmbeddingService(db_session, provider=fake_provider)
    assert len(svc.chunks_needing_embedding(doc.id, version.id)) == 2
    first = svc.embed_version(doc.id, version.id)
    assert first.chunks_embedded == 2
    second = svc.embed_version(doc.id, version.id)
    assert second.status == "UP_TO_DATE"
    assert second.chunks_embedded == 0
    assert second.chunks_skipped == 2
    assert svc.chunks_needing_embedding(doc.id, version.id) == []


def test_content_change_triggers_reembed(
    db_session: Session, fake_provider: FakeEmbeddingProvider
) -> None:
    doc, version, chunks, _ = _seed_chunks(db_session, n=1)
    svc = PolicyEmbeddingService(db_session, provider=fake_provider)
    svc.embed_version(doc.id, version.id)
    chunk = db_session.get(PolicyChunk, chunks[0].id)
    assert chunk is not None
    chunk.content = "Completely revised policy text about freight allowances."
    chunk.content_hash = content_sha256(chunk.content)
    db_session.commit()
    pending = svc.chunks_needing_embedding(doc.id, version.id)
    assert len(pending) == 1
    again = svc.embed_version(doc.id, version.id)
    assert again.chunks_embedded == 1
    db_session.refresh(chunk)
    assert chunk.embedding_content_hash == chunk.content_hash


def test_model_change_triggers_reembed(db_session: Session) -> None:
    doc, version, _, _ = _seed_chunks(db_session, n=1)
    a = FakeEmbeddingProvider(model="model-a", dimension=DIM)
    b = FakeEmbeddingProvider(model="model-b", dimension=DIM)
    PolicyEmbeddingService(db_session, provider=a).embed_version(doc.id, version.id)
    svc_b = PolicyEmbeddingService(db_session, provider=b)
    assert len(svc_b.chunks_needing_embedding(doc.id, version.id)) == 1
    result = svc_b.embed_version(doc.id, version.id)
    assert result.chunks_embedded == 1
    assert result.embedding_model == "model-b"


def test_batch_embedding(db_session: Session) -> None:
    provider = FakeEmbeddingProvider(dimension=DIM)
    settings = Settings(embedding_batch_size=2, embedding_dimension=DIM)
    doc, version, _, _ = _seed_chunks(db_session, n=5)
    svc = PolicyEmbeddingService(db_session, provider=provider, settings=settings)
    result = svc.embed_version(doc.id, version.id)
    assert result.chunks_embedded == 5
    chunks = list(
        db_session.scalars(
            select(PolicyChunk).where(PolicyChunk.policy_version_id == version.id)
        )
    )
    assert all(c.embedding is not None for c in chunks)


def test_provider_failure_does_not_mark_embedded(db_session: Session) -> None:
    doc, version, _, _ = _seed_chunks(db_session, n=2)
    failing = _FailingProvider()
    svc = PolicyEmbeddingService(db_session, provider=failing)
    with pytest.raises(EmbeddingProviderError):
        svc.embed_version(doc.id, version.id)
    chunks = list(
        db_session.scalars(
            select(PolicyChunk).where(PolicyChunk.policy_version_id == version.id)
        )
    )
    assert all(c.embedding is None for c in chunks)
    assert all(c.embedding_model is None for c in chunks)


def test_retrieval_relevance_topk_provenance_ordering(
    db_session: Session, fake_provider: FakeEmbeddingProvider
) -> None:
    doc, version, _, _ = _seed_chunks(db_session, n=3)
    PolicyEmbeddingService(db_session, provider=fake_provider).embed_version(doc.id, version.id)
    retrieval = PolicyRetrievalService(db_session, provider=fake_provider)

    hits = retrieval.retrieve_policy_chunks(
        "unit price variance percent purchase order",
        top_k=2,
        policy_version_id=version.id,
    )
    assert len(hits) == 2
    assert hits[0].similarity >= hits[1].similarity
    assert "price" in hits[0].content.lower() or "variance" in hits[0].content.lower()

    # Provenance
    hit = hits[0]
    assert hit.chunk_id is not None
    assert hit.policy_document_id == doc.id
    assert hit.policy_version_id == version.id
    assert hit.content_hash
    assert hit.embedding_model == fake_provider.model
    assert hit.source_filename == "policy.md"
    assert hit.section_id is not None

    # Deterministic ordering for fixed query/dataset
    again = retrieval.retrieve_policy_chunks(
        "unit price variance percent purchase order",
        top_k=2,
        policy_version_id=version.id,
    )
    assert [h.chunk_id for h in again] == [h.chunk_id for h in hits]


def test_version_filter_and_empty_kb(
    db_session: Session, fake_provider: FakeEmbeddingProvider
) -> None:
    doc, version, _, _ = _seed_chunks(db_session, n=2)
    PolicyEmbeddingService(db_session, provider=fake_provider).embed_version(doc.id, version.id)
    retrieval = PolicyRetrievalService(db_session, provider=fake_provider)

    doc2 = PolicyService(db_session).create_document(name=f"Empty-{uuid4().hex[:8]}")
    empty_version = PolicyService(db_session).create_version(
        doc2.id,
        version_label="e1",
        effective_from=date(2026, 1, 1),
        source_content="empty",
    )
    empty_hits = retrieval.retrieve_policy_chunks(
        "price variance",
        top_k=5,
        policy_version_id=empty_version.id,
    )
    assert empty_hits == []

    scoped = retrieval.retrieve_policy_chunks(
        "price variance",
        top_k=5,
        policy_document_id=doc.id,
        policy_version_id=version.id,
    )
    assert scoped
    assert all(h.policy_version_id == version.id for h in scoped)


def test_embed_and_search_api(
    api_client: TestClient,
    db_session: Session,
    fake_provider: FakeEmbeddingProvider,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _embed_svc(session: Session, **_kwargs):
        return PolicyEmbeddingService(session, provider=fake_provider)

    def _retrieval_svc(session: Session, **_kwargs):
        return PolicyRetrievalService(session, provider=fake_provider)

    monkeypatch.setattr("app.api.routes.policies.PolicyEmbeddingService", _embed_svc)
    monkeypatch.setattr("app.api.routes.policies.PolicyRetrievalService", _retrieval_svc)

    doc, version, _, _ = _seed_chunks(db_session, n=3)

    embed_resp = api_client.post(f"/policies/{doc.id}/versions/{version.id}/embed")
    assert embed_resp.status_code == 200
    body = embed_resp.json()
    assert body["status"] == "EMBEDDED"
    assert body["chunks_embedded"] == 3

    search_resp = api_client.post(
        f"/policies/{doc.id}/versions/{version.id}/search",
        json={"query": "price variance unit price", "top_k": 2},
    )
    assert search_resp.status_code == 200
    search = search_resp.json()
    assert search["count"] == 2
    assert search["items"][0]["content"]
    assert "similarity" in search["items"][0]
    assert search["items"][0]["policy_document_id"] == str(doc.id)


@pytest.mark.live_embedding
def test_live_gemini_embedding_and_retrieval(db_session: Session) -> None:
    import os

    from app.core.config import get_settings
    from app.embeddings.gemini import GeminiEmbeddingProvider

    get_settings.cache_clear()
    api_key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not api_key:
        pytest.skip("GEMINI_API_KEY not configured")

    settings = Settings(
        gemini_api_key=api_key,
        embedding_model="gemini-embedding-001",
        embedding_dimension=DIM,
        embedding_batch_size=8,
    )
    provider = GeminiEmbeddingProvider(settings)
    try:
        vector = provider.embed_text("Price variance tolerance is two percent.")
    except EmbeddingProviderError as exc:
        if exc.code == "AUTH_ERROR":
            pytest.fail(
                "GEMINI_API_KEY was rejected by Google (AUTH_ERROR). "
                "Use a Gemini API key from Google AI Studio."
            )
        raise
    assert len(vector) == DIM

    doc, version, _, _ = _seed_chunks(db_session, n=3)
    PolicyEmbeddingService(db_session, provider=provider, settings=settings).embed_version(
        doc.id, version.id
    )
    retrieval = PolicyRetrievalService(db_session, provider=provider, settings=settings)
    hits = retrieval.retrieve_policy_chunks(
        "What is the allowed unit price variance?",
        top_k=1,
        policy_version_id=version.id,
    )
    assert hits
    assert "price" in hits[0].content.lower() or "variance" in hits[0].content.lower()
