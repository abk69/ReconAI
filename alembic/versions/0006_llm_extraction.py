"""Add llm_extraction_results for M6 Gemini-assisted extractions.

Revision ID: 0006_llm_extraction
Revises: 0005_review_tasks
Create Date: 2026-09-19

Stores Gemini candidates, comparison, evidence checks, and usage metadata
separately so M4 DocumentExtractionResult rows are never overwritten.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_llm_extraction"
down_revision: str | Sequence[str] | None = "0005_review_tasks"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "llm_extraction_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("m4_extraction_result_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("invocation_status", sa.String(length=64), nullable=False),
        sa.Column("application_quality", sa.String(length=32), nullable=True),
        sa.Column("quality_reasons", JsonDocument, nullable=False),
        sa.Column("gate_reasons", JsonDocument, nullable=False),
        sa.Column("candidate", JsonDocument, nullable=True),
        sa.Column("evidence", JsonDocument, nullable=False),
        sa.Column("validation", JsonDocument, nullable=False),
        sa.Column("comparison", JsonDocument, nullable=True),
        sa.Column("evidence_check", JsonDocument, nullable=True),
        sa.Column("usage", JsonDocument, nullable=True),
        sa.Column("provider_metadata", JsonDocument, nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["m4_extraction_result_id"],
            ["document_extraction_results.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_extraction_results_document_id",
        "llm_extraction_results",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_llm_extraction_results_m4_extraction_result_id"),
        "llm_extraction_results",
        ["m4_extraction_result_id"],
        unique=False,
    )
    op.create_index(
        "ix_llm_extraction_results_invocation_status",
        "llm_extraction_results",
        ["invocation_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_extraction_results_invocation_status",
        table_name="llm_extraction_results",
    )
    op.drop_index(
        op.f("ix_llm_extraction_results_m4_extraction_result_id"),
        table_name="llm_extraction_results",
    )
    op.drop_index("ix_llm_extraction_results_document_id", table_name="llm_extraction_results")
    op.drop_table("llm_extraction_results")
