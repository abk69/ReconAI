"""Add fingerprint for idempotent reconciliation exceptions.

Revision ID: 0002_exception_fingerprint
Revises: 0001_initial_schema
Create Date: 2026-09-17

Why: Re-running the same reconciliation must not create uncontrolled duplicate
exception rows. A stable ``fingerprint`` unique key lets the service upsert by
identity without relying on fragile JSON comparisons.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_exception_fingerprint"
down_revision: str | Sequence[str] | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reconciliation_exceptions",
        sa.Column("fingerprint", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_reconciliation_exceptions_fingerprint",
        "reconciliation_exceptions",
        ["fingerprint"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reconciliation_exceptions_fingerprint",
        table_name="reconciliation_exceptions",
    )
    op.drop_column("reconciliation_exceptions", "fingerprint")
