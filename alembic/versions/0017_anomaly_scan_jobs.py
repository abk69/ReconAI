"""Add anomaly_scan_jobs and pagination index (M9.2).

Revision ID: 0017_anomaly_scan_jobs
Revises: 0016_anomaly_signals
Create Date: 2026-09-22

Bounded resumable batch scans + cursor pagination support index.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_anomaly_scan_jobs"
down_revision: str | Sequence[str] | None = "0016_anomaly_signals"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "anomaly_scan_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scan_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scan_key", sa.String(length=128), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cursor", sa.String(length=128), nullable=True),
        sa.Column("processed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("anomaly_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("scan_type", "scan_key", name="uq_anomaly_scan_jobs_type_key"),
    )
    op.create_index("ix_anomaly_scan_jobs_status", "anomaly_scan_jobs", ["status"])
    op.create_index("ix_anomaly_scan_jobs_scan_type", "anomaly_scan_jobs", ["scan_type"])
    op.create_index(
        "ix_anomaly_scan_jobs_requested_at", "anomaly_scan_jobs", ["requested_at"]
    )
    op.create_index(
        "ix_anomaly_signals_detected_at_id",
        "anomaly_signals",
        ["detected_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_anomaly_signals_detected_at_id", table_name="anomaly_signals")
    op.drop_index("ix_anomaly_scan_jobs_requested_at", table_name="anomaly_scan_jobs")
    op.drop_index("ix_anomaly_scan_jobs_scan_type", table_name="anomaly_scan_jobs")
    op.drop_index("ix_anomaly_scan_jobs_status", table_name="anomaly_scan_jobs")
    op.drop_table("anomaly_scan_jobs")
