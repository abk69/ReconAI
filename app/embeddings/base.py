"""Embedding provider abstraction — policy services depend on this, not Gemini SDK."""

from __future__ import annotations

from abc import ABC, abstractmethod
from math import sqrt


class EmbeddingProviderError(Exception):
    """Provider-level embedding failure (auth, timeout, dimension mismatch, etc.)."""

    def __init__(self, message: str, *, code: str = "PROVIDER_ERROR") -> None:
        super().__init__(message)
        self.code = code


class EmbeddingProvider(ABC):
    """Interface for text → dense vector embedding."""

    @property
    @abstractmethod
    def model(self) -> str:
        """Model identifier stored alongside embeddings for staleness checks."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Expected vector length (must match pgvector column)."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embed a single text; returns an L2-normalized vector of ``dimension`` floats."""

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Embed many texts. Default loops ``embed_text``; providers may batch."""
        return [self.embed_text(t) for t in texts]


def l2_normalize(vector: list[float]) -> list[float]:
    """Return an L2-normalized copy; zero vectors stay zero."""
    norm = sqrt(sum(v * v for v in vector))
    if norm == 0.0:
        return list(vector)
    return [v / norm for v in vector]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """Cosine distance for unit (or near-unit) vectors: ``1 - dot(a, b)`` clamped."""
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    # Clamp numerical noise for nearly-identical unit vectors.
    if dot > 1.0:
        dot = 1.0
    elif dot < -1.0:
        dot = -1.0
    return 1.0 - dot


def assert_embedding_dimension(vector: list[float], expected: int) -> None:
    if len(vector) != expected:
        raise EmbeddingProviderError(
            f"Embedding dimension mismatch: got {len(vector)}, expected {expected}.",
            code="DIMENSION_MISMATCH",
        )
