"""Record worker queue polls.

Revision ID: 0020_worker_heartbeats
Revises: 0019_identity_and_jobs
Create Date: 2026-10-26

The API reads this table to tell a live worker from one that has stopped.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020_worker_heartbeats"
down_revision: str | Sequence[str] | None = "0019_identity_and_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.String(length=64), primary_key=True),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
