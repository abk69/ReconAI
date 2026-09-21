"""Add approved_parameters_hash for M8.5 approved-action immutability.

Revision ID: 0014_approved_parameters_hash
Revises: 0013_resolution_approval
Create Date: 2026-09-21

Stores a SHA-256 digest of canonical ProposedAction.parameters at approval time
so execution can verify the payload matches what the human authorized.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_approved_parameters_hash"
down_revision: str | Sequence[str] | None = "0013_resolution_approval"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("proposed_actions") as batch:
        batch.add_column(
            sa.Column("approved_parameters_hash", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("proposed_actions") as batch:
        batch.drop_column("approved_parameters_hash")
