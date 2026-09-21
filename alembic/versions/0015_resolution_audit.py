"""Add append-only resolution_audit_events table (M8.6).

Revision ID: 0015_resolution_audit
Revises: 0014_approved_parameters_hash
Create Date: 2026-09-21

Durable audit trail for plan → propose → approve → execute → workflow.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_resolution_audit"
down_revision: str | Sequence[str] | None = "0014_approved_parameters_hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "resolution_audit_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("resolution_plan_id", sa.Uuid(), nullable=True),
        sa.Column("proposed_action_id", sa.Uuid(), nullable=True),
        sa.Column("action_execution_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("actor_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=255), nullable=True),
        sa.Column("event_data", JsonDocument, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["resolution_plan_id"],
            ["resolution_plans.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_action_id"],
            ["proposed_actions.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["action_execution_id"],
            ["action_executions.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_resolution_audit_events_plan_id",
        "resolution_audit_events",
        ["resolution_plan_id"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_audit_events_action_id",
        "resolution_audit_events",
        ["proposed_action_id"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_audit_events_execution_id",
        "resolution_audit_events",
        ["action_execution_id"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_audit_events_event_type",
        "resolution_audit_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_resolution_audit_events_created_at",
        "resolution_audit_events",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_resolution_audit_events_created_at", table_name="resolution_audit_events")
    op.drop_index("ix_resolution_audit_events_event_type", table_name="resolution_audit_events")
    op.drop_index("ix_resolution_audit_events_execution_id", table_name="resolution_audit_events")
    op.drop_index("ix_resolution_audit_events_action_id", table_name="resolution_audit_events")
    op.drop_index("ix_resolution_audit_events_plan_id", table_name="resolution_audit_events")
    op.drop_table("resolution_audit_events")
