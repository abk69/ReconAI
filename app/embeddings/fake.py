"""Deterministic fake embedding provider for offline tests (no Gemini)."""

from __future__ import annotations

import hashlib
import re

from app.embeddings.base import EmbeddingProvider, l2_normalize

_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)


class FakeEmbeddingProvider(EmbeddingProvider):
    """Hash / bag-of-words style embeddings — deterministic and offline.

    Shared vocabulary yields higher cosine similarity so retrieval tests work
    without a live API.
    """

    def __init__(self, *, model: str = "fake-embedding", dimension: int = 768) -> None:
        self._model = model
        self._dimension = dimension

    @property
    def model(self) -> str:
        return self._model

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        # Same space as documents for the fake provider.
        return self.embed_text(text)

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dimension
        tokens = _TOKEN.findall(text.lower())
        if not tokens:
            # Stable non-zero vector for empty-ish text.
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            for i, byte in enumerate(digest):
                vec[i % self._dimension] += (byte / 255.0) - 0.5
            return l2_normalize(vec)

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            # Spread each token across a few dimensions for smoother similarity.
            for offset in range(4):
                idx = int.from_bytes(digest[offset * 2 : offset * 2 + 2], "big") % self._dimension
                sign = 1.0 if digest[8 + offset] % 2 == 0 else -1.0
                vec[idx] += sign
        return l2_normalize(vec)
