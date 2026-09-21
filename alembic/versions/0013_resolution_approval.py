"""Add approval idempotency key for M8.4 human approval gate.

Revision ID: 0013_resolution_approval
Revises: 0012_resolution_planner
Create Date: 2026-09-21

Append-only ActionApproval rows gain an optional unique idempotency_key so
duplicate approval retries return the same decision without rewriting history.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_resolution_approval"
down_revision: str | Sequence[str] | None = "0012_resolution_planner"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("action_approvals") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint(
            "uq_action_approvals_idempotency_key",
            ["idempotency_key"],
        )


def downgrade() -> None:
    with op.batch_alter_table("action_approvals") as batch:
        batch.drop_constraint("uq_action_approvals_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
