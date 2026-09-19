"""Policy chunk embedding persistence (M7.3) — no retrieval, no generation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import PolicyChunk
from app.embeddings.base import (
    EmbeddingProvider,
    EmbeddingProviderError,
    assert_embedding_dimension,
)
from app.embeddings.gemini import GeminiEmbeddingProvider
from app.services.policy_service import PolicyService


@dataclass(frozen=True)
class EmbedSummary:
    policy_id: UUID
    version_id: UUID
    chunks_total: int
    chunks_embedded: int
    chunks_skipped: int
    embedding_model: str
    status: str
    message: str | None = None


class PolicyEmbeddingService:
    """Generate and persist embeddings for policy chunks that need them."""

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

    @property
    def model(self) -> str:
        return self._provider.model

    def chunks_needing_embedding(
        self,
        policy_id: UUID,
        version_id: UUID,
    ) -> list[PolicyChunk]:
        chunks = self._policies.list_chunks(policy_id, version_id)
        return [c for c in chunks if self._is_stale(c)]

    def embed_version(self, policy_id: UUID, version_id: UUID) -> EmbedSummary:
        """Embed missing/stale chunks for a version. Explicit operation (not on GET)."""
        self._policies.get_version(policy_id, version_id)
        all_chunks = self._policies.list_chunks(policy_id, version_id)
        if not all_chunks:
            return EmbedSummary(
                policy_id=policy_id,
                version_id=version_id,
                chunks_total=0,
                chunks_embedded=0,
                chunks_skipped=0,
                embedding_model=self.model,
                status="EMPTY",
                message="No chunks to embed.",
            )

        pending = [c for c in all_chunks if self._is_stale(c)]
        skipped = len(all_chunks) - len(pending)
        if not pending:
            return EmbedSummary(
                policy_id=policy_id,
                version_id=version_id,
                chunks_total=len(all_chunks),
                chunks_embedded=0,
                chunks_skipped=skipped,
                embedding_model=self.model,
                status="UP_TO_DATE",
                message="All chunk embeddings are current.",
            )

        batch_size = self._settings.embedding_batch_size
        embedded = 0
        for start in range(0, len(pending), batch_size):
            batch = pending[start : start + batch_size]
            try:
                vectors = self._provider.embed_texts([c.content for c in batch])
            except EmbeddingProviderError:
                # No writes for this failed batch; earlier batches already committed.
                raise

            if len(vectors) != len(batch):
                raise EmbeddingProviderError(
                    "Provider returned unexpected embedding count.",
                    code="MALFORMED_RESPONSE",
                )

            now = datetime.now(UTC)
            for chunk, vector in zip(batch, vectors, strict=True):
                assert_embedding_dimension(vector, self._provider.dimension)
                chunk.embedding = vector
                chunk.embedding_model = self.model
                chunk.embedding_content_hash = chunk.content_hash
                chunk.embedded_at = now

            try:
                self._session.commit()
            except Exception:
                self._session.rollback()
                raise
            embedded += len(batch)

        return EmbedSummary(
            policy_id=policy_id,
            version_id=version_id,
            chunks_total=len(all_chunks),
            chunks_embedded=embedded,
            chunks_skipped=skipped,
            embedding_model=self.model,
            status="EMBEDDED",
            message=f"Embedded {embedded} chunk(s); skipped {skipped} current.",
        )

    def _is_stale(self, chunk: PolicyChunk) -> bool:
        if chunk.embedding is None:
            return True
        if chunk.embedding_content_hash != chunk.content_hash:
            return True
        if chunk.embedding_model != self.model:
            return True
        return len(chunk.embedding) != self._provider.dimension
