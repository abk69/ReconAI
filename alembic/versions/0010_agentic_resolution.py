"""Add agentic resolution plan/action/approval/execution tables (M8.1).

Revision ID: 0010_agentic_resolution
Revises: 0009_policy_grounding
Create Date: 2026-09-19

Controlled workflow orchestration only. Does not alter M2 financial tables
or allow LLM-driven mutation of procurement records.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010_agentic_resolution"
down_revision: str | Sequence[str] | None = "0009_policy_grounding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "resolution_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_exception_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reasoning_summary", sa.Text(), nullable=False),
        sa.Column("policy_grounding_result_id", sa.Uuid(), nullable=True),
        sa.Column("proposed_by", sa.String(length=255), nullable=True),
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
            ["reconciliation_exception_id"],
            ["reconciliation_exceptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["policy_grounding_result_id"],
            ["policy_grounding_results.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resolution_plans_exception_id",
        "resolution_plans",
        ["reconciliation_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_plans_status",
        "resolution_plans",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_plans_policy_grounding_result_id",
        "resolution_plans",
        ["policy_grounding_result_id"],
        unique=False,
    )

    op.create_table(
        "proposed_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resolution_plan_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=64), nullable=False),
        sa.Column("action_order", sa.Integer(), nullable=False),
        sa.Column("parameters", JsonDocument, nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
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
            ["resolution_plan_id"],
            ["resolution_plans.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resolution_plan_id",
            "action_order",
            name="uq_proposed_actions_plan_order",
        ),
    )
    op.create_index(
        "ix_proposed_actions_plan_id",
        "proposed_actions",
        ["resolution_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_proposed_actions_status",
        "proposed_actions",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_proposed_actions_action_type",
        "proposed_actions",
        ["action_type"],
        unique=False,
    )

    op.create_table(
        "action_approvals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposed_action_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reviewer", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["proposed_action_id"],
            ["proposed_actions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_action_approvals_proposed_action_id",
        "action_approvals",
        ["proposed_action_id"],
        unique=False,
    )

    op.create_table(
        "action_executions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposed_action_id", sa.Uuid(), nullable=False),
        sa.Column("execution_status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", JsonDocument, nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["proposed_action_id"],
            ["proposed_actions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_action_executions_idempotency_key",
        ),
    )
    op.create_index(
        "ix_action_executions_proposed_action_id",
        "action_executions",
        ["proposed_action_id"],
        unique=False,
    )
    op.create_index(
        "ix_action_executions_status",
        "action_executions",
        ["execution_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_action_executions_status", table_name="action_executions")
    op.drop_index("ix_action_executions_proposed_action_id", table_name="action_executions")
    op.drop_table("action_executions")
    op.drop_index("ix_action_approvals_proposed_action_id", table_name="action_approvals")
    op.drop_table("action_approvals")
    op.drop_index("ix_proposed_actions_action_type", table_name="proposed_actions")
    op.drop_index("ix_proposed_actions_status", table_name="proposed_actions")
    op.drop_index("ix_proposed_actions_plan_id", table_name="proposed_actions")
    op.drop_table("proposed_actions")
    op.drop_index("ix_resolution_plans_policy_grounding_result_id", table_name="resolution_plans")
    op.drop_index("ix_resolution_plans_status", table_name="resolution_plans")
    op.drop_index("ix_resolution_plans_exception_id", table_name="resolution_plans")
    op.drop_table("resolution_plans")
