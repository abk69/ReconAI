"""Add review_tasks and review_decisions for M5 human review.

Revision ID: 0005_review_tasks
Revises: 0004_document_extraction
Create Date: 2026-09-17

Stores human review queue items and immutable field-level audit decisions.
Original M4 extraction candidates are never overwritten by review.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_review_tasks"
down_revision: str | Sequence[str] | None = "0004_document_extraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("extraction_result_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("reviewed_candidate", JsonDocument, nullable=True),
        sa.Column("promoted_entity_type", sa.String(length=32), nullable=True),
        sa.Column("promoted_entity_id", sa.Uuid(), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["extraction_result_id"],
            ["document_extraction_results.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "extraction_result_id",
            name="uq_review_tasks_extraction_result_id",
        ),
    )
    op.create_index(
        op.f("ix_review_tasks_document_id"),
        "review_tasks",
        ["document_id"],
        unique=False,
    )
    op.create_index(
        "ix_review_tasks_status",
        "review_tasks",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_review_tasks_priority",
        "review_tasks",
        ["priority"],
        unique=False,
    )
    op.create_index(
        op.f("ix_review_tasks_extraction_result_id"),
        "review_tasks",
        ["extraction_result_id"],
        unique=False,
    )

    op.create_table(
        "review_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("review_task_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("field_path", sa.String(length=255), nullable=True),
        sa.Column("original_value", JsonDocument, nullable=True),
        sa.Column("corrected_value", JsonDocument, nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("reviewer", sa.String(length=255), nullable=True),
        sa.Column("evidence_ref", sa.String(length=512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["review_task_id"], ["review_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_decisions_review_task_id"),
        "review_decisions",
        ["review_task_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_review_decisions_review_task_id"),
        table_name="review_decisions",
    )
    op.drop_table("review_decisions")
    op.drop_index(op.f("ix_review_tasks_extraction_result_id"), table_name="review_tasks")
    op.drop_index("ix_review_tasks_priority", table_name="review_tasks")
    op.drop_index("ix_review_tasks_status", table_name="review_tasks")
    op.drop_index(op.f("ix_review_tasks_document_id"), table_name="review_tasks")
    op.drop_table("review_tasks")
