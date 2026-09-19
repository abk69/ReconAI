"""Add policy knowledge-base tables for M7.1 foundation.

Revision ID: 0007_policy_knowledge
Revises: 0006_llm_extraction
Create Date: 2026-09-19

Stores versioned policy documents and provenance-preserving chunks.
Embeddings / pgvector / retrieval are intentionally deferred.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_policy_knowledge"
down_revision: str | Sequence[str] | None = "0006_llm_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_policy_documents_name"),
    )
    op.create_index("ix_policy_documents_name", "policy_documents", ["name"], unique=False)

    op.create_table(
        "policy_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_document_id", sa.Uuid(), nullable=False),
        sa.Column("version_label", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column("source_reference", sa.String(length=512), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["policy_document_id"],
            ["policy_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "policy_document_id",
            "version_label",
            name="uq_policy_versions_document_version_label",
        ),
    )
    op.create_index(
        op.f("ix_policy_versions_policy_document_id"),
        "policy_versions",
        ["policy_document_id"],
        unique=False,
    )
    op.create_index("ix_policy_versions_status", "policy_versions", ["status"], unique=False)
    op.create_index(
        "ix_policy_versions_effective_from",
        "policy_versions",
        ["effective_from"],
        unique=False,
    )

    op.create_table(
        "policy_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_version_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_id", sa.String(length=128), nullable=True),
        sa.Column("section_title", sa.String(length=512), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_filename", sa.String(length=512), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["policy_version_id"],
            ["policy_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "policy_version_id",
            "chunk_index",
            name="uq_policy_chunks_version_chunk_index",
        ),
    )
    op.create_index(
        op.f("ix_policy_chunks_policy_version_id"),
        "policy_chunks",
        ["policy_version_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_chunks_section_id",
        "policy_chunks",
        ["section_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_policy_chunks_section_id", table_name="policy_chunks")
    op.drop_index(op.f("ix_policy_chunks_policy_version_id"), table_name="policy_chunks")
    op.drop_table("policy_chunks")
    op.drop_index("ix_policy_versions_effective_from", table_name="policy_versions")
    op.drop_index("ix_policy_versions_status", table_name="policy_versions")
    op.drop_index(op.f("ix_policy_versions_policy_document_id"), table_name="policy_versions")
    op.drop_table("policy_versions")
    op.drop_index("ix_policy_documents_name", table_name="policy_documents")
    op.drop_table("policy_documents")
