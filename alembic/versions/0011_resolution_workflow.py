"""Add M8.2 resolution workflow request tables.

Revision ID: 0011_resolution_workflow
Revises: 0010_agentic_resolution
Create Date: 2026-09-19

Durable workflow records for safe action handlers. No financial mutations,
no external notifications.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_resolution_workflow"
down_revision: str | Sequence[str] | None = "0010_agentic_resolution"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "exception_review_routes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_exception_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_action_id", sa.Uuid(), nullable=False),
        sa.Column("review_queue", sa.String(length=128), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("assigned_to", sa.String(length=255), nullable=True),
        sa.Column("review_task_id", sa.Uuid(), nullable=True),
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
            ["reconciliation_exception_id"],
            ["reconciliation_exceptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_action_id"],
            ["proposed_actions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["review_task_id"],
            ["review_tasks.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposed_action_id",
            name="uq_exception_review_routes_proposed_action_id",
        ),
    )
    op.create_index(
        "ix_exception_review_routes_exception_id",
        "exception_review_routes",
        ["reconciliation_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_exception_review_routes_status",
        "exception_review_routes",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_exception_review_routes_review_task_id",
        "exception_review_routes",
        ["review_task_id"],
        unique=False,
    )

    op.create_table(
        "vendor_clarification_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_exception_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_action_id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("vendor_reference", sa.String(length=255), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("fields", JsonDocument, nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
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
            ["reconciliation_exception_id"],
            ["reconciliation_exceptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_action_id"],
            ["proposed_actions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposed_action_id",
            name="uq_vendor_clarification_requests_proposed_action_id",
        ),
    )
    op.create_index(
        "ix_vendor_clarification_requests_exception_id",
        "vendor_clarification_requests",
        ["reconciliation_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_vendor_clarification_requests_status",
        "vendor_clarification_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_vendor_clarification_requests_vendor_id",
        "vendor_clarification_requests",
        ["vendor_id"],
        unique=False,
    )

    op.create_table(
        "missing_document_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_exception_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_action_id", sa.Uuid(), nullable=False),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("vendor_reference", sa.String(length=255), nullable=True),
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
            ["reconciliation_exception_id"],
            ["reconciliation_exceptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_action_id"],
            ["proposed_actions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["vendor_id"],
            ["vendors.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposed_action_id",
            name="uq_missing_document_requests_proposed_action_id",
        ),
    )
    op.create_index(
        "ix_missing_document_requests_exception_id",
        "missing_document_requests",
        ["reconciliation_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_missing_document_requests_status",
        "missing_document_requests",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_missing_document_requests_vendor_id",
        "missing_document_requests",
        ["vendor_id"],
        unique=False,
    )

    op.create_table(
        "manager_escalations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("reconciliation_exception_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_action_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=16), nullable=False),
        sa.Column("destination", sa.String(length=128), nullable=True),
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
            ["reconciliation_exception_id"],
            ["reconciliation_exceptions.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_action_id"],
            ["proposed_actions.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proposed_action_id",
            name="uq_manager_escalations_proposed_action_id",
        ),
    )
    op.create_index(
        "ix_manager_escalations_exception_id",
        "manager_escalations",
        ["reconciliation_exception_id"],
        unique=False,
    )
    op.create_index(
        "ix_manager_escalations_status",
        "manager_escalations",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_manager_escalations_priority",
        "manager_escalations",
        ["priority"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_manager_escalations_priority", table_name="manager_escalations")
    op.drop_index("ix_manager_escalations_status", table_name="manager_escalations")
    op.drop_index("ix_manager_escalations_exception_id", table_name="manager_escalations")
    op.drop_table("manager_escalations")
    op.drop_index("ix_missing_document_requests_vendor_id", table_name="missing_document_requests")
    op.drop_index("ix_missing_document_requests_status", table_name="missing_document_requests")
    op.drop_index(
        "ix_missing_document_requests_exception_id",
        table_name="missing_document_requests",
    )
    op.drop_table("missing_document_requests")
    op.drop_index(
        "ix_vendor_clarification_requests_vendor_id",
        table_name="vendor_clarification_requests",
    )
    op.drop_index(
        "ix_vendor_clarification_requests_status",
        table_name="vendor_clarification_requests",
    )
    op.drop_index(
        "ix_vendor_clarification_requests_exception_id",
        table_name="vendor_clarification_requests",
    )
    op.drop_table("vendor_clarification_requests")
    op.drop_index(
        "ix_exception_review_routes_review_task_id",
        table_name="exception_review_routes",
    )
    op.drop_index("ix_exception_review_routes_status", table_name="exception_review_routes")
    op.drop_index(
        "ix_exception_review_routes_exception_id",
        table_name="exception_review_routes",
    )
    op.drop_table("exception_review_routes")
