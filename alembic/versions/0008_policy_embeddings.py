"""Add pgvector embeddings columns to policy_chunks (M7.3).

Revision ID: 0008_policy_embeddings
Revises: 0007_policy_knowledge
Create Date: 2026-09-19

Enables the ``vector`` extension on PostgreSQL and adds nullable embedding
storage plus staleness metadata. Dimension is fixed at 768 to match
``DEFAULT_EMBEDDING_DIMENSION`` / Settings ``embedding_dimension``.

No approximate (HNSW/IVFFlat) index: portfolio-scale datasets are small enough
that exact cosine distance scans are simpler and fully deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_policy_embeddings"
down_revision: str | Sequence[str] | None = "0007_policy_knowledge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Keep in sync with app.embeddings.constants.DEFAULT_EMBEDDING_DIMENSION
_EMBEDDING_DIM = 768


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
        from pgvector.sqlalchemy import Vector

        embedding_type: sa.types.TypeEngine = Vector(_EMBEDDING_DIM)
    else:
        # SQLite / offline Alembic tests store the vector as JSON array.
        embedding_type = sa.JSON()

    op.add_column("policy_chunks", sa.Column("embedding", embedding_type, nullable=True))
    op.add_column(
        "policy_chunks",
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "policy_chunks",
        sa.Column("embedding_content_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "policy_chunks",
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("policy_chunks", "embedded_at")
    op.drop_column("policy_chunks", "embedding_content_hash")
    op.drop_column("policy_chunks", "embedding_model")
    op.drop_column("policy_chunks", "embedding")
    # Leave the vector extension installed on PostgreSQL (safe / shared).
