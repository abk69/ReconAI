"""Shared embedding dimension / model defaults.

Must match:
- Alembic migration ``0008_policy_embeddings`` (``vector(N)``)
- Settings ``embedding_dimension`` / ``embedding_model`` defaults
- Gemini ``output_dimensionality`` request

``gemini-embedding-001`` defaults to 3072 dims; we request 768 (recommended MRL size)
and L2-normalize so cosine distance is valid (Google docs require manual norm for
non-3072 dims on embedding-001).
"""

DEFAULT_EMBEDDING_DIMENSION = 768
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
