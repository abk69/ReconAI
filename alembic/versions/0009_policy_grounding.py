"""Add policy_grounding_results audit table (M7.4).

Revision ID: 0009_policy_grounding
Revises: 0008_policy_embeddings
Create Date: 2026-09-19

Stores AI-derived grounded policy explanations linked to reconciliation
exceptions. Does not modify exception status or financial facts.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_policy_grounding"
down_revision: str | Sequence[str] | None = "0008_policy_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "policy_grounding_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_exception_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("conclusion", sa.Text(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("policy_support", sa.Text(), nullable=False),
        sa.Column("limitations", sa.Text(), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
        sa.Column("retrieved_chunk_ids", sa.JSON(), nullable=False),
        sa.Column("retrieval_query", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reconciliation_exception_id"],
            ["reconciliation_exceptions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_policy_grounding_results_exception_id",
        "policy_grounding_results",
        ["reconciliation_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_policy_grounding_results_status",
        "policy_grounding_results",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_policy_grounding_results_status", table_name="policy_grounding_results")
    op.drop_index(
        "ix_policy_grounding_results_exception_id",
        table_name="policy_grounding_results",
    )
    op.drop_table("policy_grounding_results")
