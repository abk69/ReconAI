"""Add M8.3 AI resolution planner metadata and attempt audit.

Revision ID: 0012_resolution_planner
Revises: 0011_resolution_workflow
Create Date: 2026-09-21

Planner metadata on resolution_plans plus resolution_planning_attempts for
idempotency and failure audit. Plans never execute actions.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_resolution_planner"
down_revision: str | Sequence[str] | None = "0011_resolution_workflow"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("resolution_plans") as batch:
        batch.add_column(sa.Column("planning_key", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("planner_model", sa.String(length=128), nullable=True))
        batch.add_column(sa.Column("prompt_version", sa.String(length=64), nullable=True))
        batch.add_column(
            sa.Column(
                "provider_metadata",
                JsonDocument,
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch.add_column(sa.Column("planning_latency_ms", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("limitations", sa.Text(), nullable=False, server_default="")
        )
        batch.create_unique_constraint(
            "uq_resolution_plans_planning_key",
            ["planning_key"],
        )

    op.create_table(
        "resolution_planning_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_exception_id", sa.Uuid(), nullable=False),
        sa.Column("planning_key", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resolution_plan_id", sa.Uuid(), nullable=True),
        sa.Column("policy_grounding_result_id", sa.Uuid(), nullable=True),
        sa.Column("planner_model", sa.String(length=128), nullable=True),
        sa.Column("prompt_version", sa.String(length=64), nullable=True),
        sa.Column("action_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider_metadata", JsonDocument, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["reconciliation_exception_id"],
            ["reconciliation_exceptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["resolution_plan_id"],
            ["resolution_plans.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["policy_grounding_result_id"],
            ["policy_grounding_results.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resolution_planning_attempts_exception_id",
        "resolution_planning_attempts",
        ["reconciliation_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_planning_attempts_planning_key",
        "resolution_planning_attempts",
        ["planning_key"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_planning_attempts_status",
        "resolution_planning_attempts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_planning_attempts_resolution_plan_id",
        "resolution_planning_attempts",
        ["resolution_plan_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_resolution_planning_attempts_resolution_plan_id",
        table_name="resolution_planning_attempts",
    )
    op.drop_index(
        "ix_resolution_planning_attempts_status",
        table_name="resolution_planning_attempts",
    )
    op.drop_index(
        "ix_resolution_planning_attempts_planning_key",
        table_name="resolution_planning_attempts",
    )
    op.drop_index(
        "ix_resolution_planning_attempts_exception_id",
        table_name="resolution_planning_attempts",
    )
    op.drop_table("resolution_planning_attempts")
    with op.batch_alter_table("resolution_plans") as batch:
        batch.drop_constraint("uq_resolution_plans_planning_key", type_="unique")
        batch.drop_column("limitations")
        batch.drop_column("planning_latency_ms")
        batch.drop_column("provider_metadata")
        batch.drop_column("prompt_version")
        batch.drop_column("planner_model")
        batch.drop_column("planning_key")
