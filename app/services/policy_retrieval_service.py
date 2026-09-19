"""Policy vector retrieval (M7.3) — evidence only, no generation."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.db.models import PolicyChunk, PolicyVersion
from app.embeddings.base import EmbeddingProvider, cosine_distance
from app.embeddings.gemini import GeminiEmbeddingProvider
from app.services.policy_service import PolicyNotFoundError, PolicyService, PolicyValidationError


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: UUID
    policy_document_id: UUID
    policy_version_id: UUID
    chunk_index: int
    content: str
    section_id: str | None
    section_title: str | None
    page_number: int | None
    source_filename: str | None
    content_hash: str
    embedding_model: str | None
    distance: float
    similarity: float


class PolicyRetrievalService:
    """Embed a query and rank policy chunks by cosine distance.

    Similarity metric
    -----------------
    Vectors are L2-normalized at write/query time. We use **cosine distance**
    (``1 - cosine_similarity``), which for unit vectors equals half the squared
    L2 distance. On PostgreSQL this maps to pgvector's ``<=>`` operator; on
    SQLite (tests) we compute the same formula in Python for identical ordering.
    """

    def __init__(
        self,
        session: Session,
        *,
        provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._provider = provider or GeminiEmbeddingProvider(self._settings)
        self._policies = PolicyService(session)

    def retrieve_policy_chunks(
        self,
        query: str,
        *,
        top_k: int = 5,
        policy_document_id: UUID | None = None,
        policy_version_id: UUID | None = None,
    ) -> list[RetrievalHit]:
        q = (query or "").strip()
        if not q:
            raise PolicyValidationError("query must not be empty.")
        if top_k < 1:
            raise PolicyValidationError("top_k must be >= 1.")

        if policy_version_id is not None and policy_document_id is not None:
            # Ensure the version belongs to the document.
            self._policies.get_version(policy_document_id, policy_version_id)
        elif policy_version_id is not None:
            version = self._session.get(PolicyVersion, policy_version_id)
            if version is None:
                raise PolicyNotFoundError(f"Policy version {policy_version_id} was not found.")
        elif policy_document_id is not None:
            self._policies.get_document(policy_document_id)

        query_vector = self._embed_query(q)
        candidates = self._load_candidates(
            policy_document_id=policy_document_id,
            policy_version_id=policy_version_id,
        )
        if not candidates:
            return []

        scored: list[tuple[float, PolicyChunk]] = []
        for chunk in candidates:
            if chunk.embedding is None:
                continue
            # Skip stale embeddings rather than ranking outdated vectors.
            if chunk.embedding_content_hash != chunk.content_hash:
                continue
            if chunk.embedding_model != self._provider.model:
                continue
            if len(chunk.embedding) != len(query_vector):
                continue
            distance = cosine_distance(list(chunk.embedding), query_vector)
            scored.append((distance, chunk))

        # Deterministic ordering: distance asc, then chunk_index, then id.
        scored.sort(key=lambda item: (item[0], item[1].chunk_index, str(item[1].id)))
        hits: list[RetrievalHit] = []
        for distance, chunk in scored[:top_k]:
            version = chunk.policy_version
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.id,
                    policy_document_id=version.policy_document_id,
                    policy_version_id=chunk.policy_version_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    section_id=chunk.section_id,
                    section_title=chunk.section_title,
                    page_number=chunk.page_number,
                    source_filename=chunk.source_filename,
                    content_hash=chunk.content_hash,
                    embedding_model=chunk.embedding_model,
                    distance=distance,
                    similarity=1.0 - distance,
                )
            )
        return hits

    def _embed_query(self, query: str) -> list[float]:
        embed_query = getattr(self._provider, "embed_query", None)
        if callable(embed_query):
            return list(embed_query(query))
        return list(self._provider.embed_text(query))

    def _load_candidates(
        self,
        *,
        policy_document_id: UUID | None,
        policy_version_id: UUID | None,
    ) -> list[PolicyChunk]:
        stmt = (
            select(PolicyChunk)
            .join(PolicyVersion, PolicyChunk.policy_version_id == PolicyVersion.id)
            .options(joinedload(PolicyChunk.policy_version))
            .where(PolicyChunk.embedding.is_not(None))
        )
        if policy_version_id is not None:
            stmt = stmt.where(PolicyChunk.policy_version_id == policy_version_id)
        if policy_document_id is not None:
            stmt = stmt.where(PolicyVersion.policy_document_id == policy_document_id)

        dialect = self._session.get_bind().dialect.name
        if dialect == "postgresql":
            # Exact cosine-distance scan (no ANN index at portfolio scale).
            # Ordering still finalized in Python for cross-dialect determinism
            # (tie-breakers). We fetch all filtered embedded chunks — fine at
            # this scale — then score in the shared path above.
            pass

        return list(self._session.scalars(stmt).unique().all())
