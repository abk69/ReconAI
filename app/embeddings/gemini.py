"""Gemini embedding provider via google-genai (M7.3)."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings, get_settings
from app.embeddings.base import (
    EmbeddingProvider,
    EmbeddingProviderError,
    assert_embedding_dimension,
    l2_normalize,
)

logger = logging.getLogger(__name__)


class GeminiEmbeddingProvider(EmbeddingProvider):
    """Embed text with Gemini ``embed_content``; no generation / RAG."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client: Any | None = None

    @property
    def model(self) -> str:
        return self._settings.embedding_model

    @property
    def dimension(self) -> int:
        return self._settings.embedding_dimension

    def _ensure_client(self) -> Any:
        api_key = self._settings.gemini_api_key
        if not api_key:
            raise EmbeddingProviderError(
                "GEMINI_API_KEY is not configured.",
                code="MISSING_API_KEY",
            )
        if self._client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise EmbeddingProviderError(
                    "google-genai package is not installed.",
                    code="SDK_MISSING",
                ) from exc
            self._client = genai.Client(api_key=api_key)
        return self._client

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._ensure_client()
        from google.genai import types

        # gemini-embedding-001: request explicit dimensionality and L2-normalize
        # truncated vectors (Google docs — required for non-3072 dims).
        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=self.dimension,
        )
        try:
            response = client.models.embed_content(
                model=self.model,
                contents=texts,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            raise _map_embedding_exception(exc) from exc

        embeddings = getattr(response, "embeddings", None) or []
        if len(embeddings) != len(texts):
            raise EmbeddingProviderError(
                f"Gemini returned {len(embeddings)} embeddings for {len(texts)} texts.",
                code="MALFORMED_RESPONSE",
            )

        vectors: list[list[float]] = []
        for emb in embeddings:
            values = list(getattr(emb, "values", None) or [])
            assert_embedding_dimension(values, self.dimension)
            vectors.append(l2_normalize(values))

        logger.info(
            "Gemini embed complete model=%s dim=%s count=%s",
            self.model,
            self.dimension,
            len(vectors),
        )
        return vectors

    def embed_query(self, text: str) -> list[float]:
        """Embed a retrieval query (task_type=RETRIEVAL_QUERY)."""
        client = self._ensure_client()
        from google.genai import types

        config = types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=self.dimension,
        )
        try:
            response = client.models.embed_content(
                model=self.model,
                contents=text,
                config=config,
            )
        except Exception as exc:  # noqa: BLE001
            raise _map_embedding_exception(exc) from exc

        embeddings = getattr(response, "embeddings", None) or []
        if not embeddings:
            raise EmbeddingProviderError(
                "Gemini returned no query embedding.",
                code="MALFORMED_RESPONSE",
            )
        values = list(getattr(embeddings[0], "values", None) or [])
        assert_embedding_dimension(values, self.dimension)
        return l2_normalize(values)


def _map_embedding_exception(exc: Exception) -> EmbeddingProviderError:
    text = str(exc).lower()
    if (
        "401" in text
        or "403" in text
        or "unauthenticated" in text
        or "api key" in text
        or "permission" in text
    ):
        return EmbeddingProviderError(f"Gemini auth failed: {exc}", code="AUTH_ERROR")
    if "429" in text or "resource_exhausted" in text or "rate" in text or "quota" in text:
        return EmbeddingProviderError(f"Gemini rate limited: {exc}", code="RATE_LIMIT")
    if "timeout" in text or "deadline" in text:
        return EmbeddingProviderError(f"Gemini timed out: {exc}", code="TIMEOUT")
    return EmbeddingProviderError(f"Gemini embedding error: {exc}", code="PROVIDER_ERROR")
