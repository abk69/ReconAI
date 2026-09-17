"""Add document_extraction_results for M4 understanding output.

Revision ID: 0004_document_extraction
Revises: 0003_documents
Create Date: 2026-09-17

Stores structured extraction/validation evidence separately from authoritative
PO/GRN/Invoice financial tables.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_document_extraction"
down_revision: str | Sequence[str] | None = "0003_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "document_extraction_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("detected_type", sa.String(length=32), nullable=False),
        sa.Column("outcome", sa.String(length=64), nullable=False),
        sa.Column("extractor_version", sa.String(length=32), nullable=False),
        sa.Column("raw_extraction", JsonDocument, nullable=False),
        sa.Column("candidate", JsonDocument, nullable=True),
        sa.Column("validation", JsonDocument, nullable=False),
        sa.Column("evidence", JsonDocument, nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_document_extraction_results_document_id"),
    )
    op.create_index(
        op.f("ix_document_extraction_results_document_id"),
        "document_extraction_results",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_document_extraction_results_outcome",
        "document_extraction_results",
        ["outcome"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_document_extraction_results_outcome",
        table_name="document_extraction_results",
    )
    op.drop_index(
        op.f("ix_document_extraction_results_document_id"),
        table_name="document_extraction_results",
    )
    op.drop_table("document_extraction_results")
