"""Add anomaly_signals table (M9.1).

Revision ID: 0016_anomaly_signals
Revises: 0015_resolution_audit
Create Date: 2026-09-21

Deterministic procurement anomaly signals — explainable risk, not fraud.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_anomaly_signals"
down_revision: str | Sequence[str] | None = "0015_resolution_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "anomaly_signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("anomaly_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("grn_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", JsonDocument, nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["purchase_order_id"], ["purchase_orders.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["grn_id"], ["goods_receipts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_anomaly_signals_fingerprint"),
    )
    op.create_index("ix_anomaly_signals_vendor_id", "anomaly_signals", ["vendor_id"])
    op.create_index("ix_anomaly_signals_invoice_id", "anomaly_signals", ["invoice_id"])
    op.create_index(
        "ix_anomaly_signals_purchase_order_id",
        "anomaly_signals",
        ["purchase_order_id"],
    )
    op.create_index("ix_anomaly_signals_anomaly_type", "anomaly_signals", ["anomaly_type"])
    op.create_index("ix_anomaly_signals_severity", "anomaly_signals", ["severity"])
    op.create_index("ix_anomaly_signals_detected_at", "anomaly_signals", ["detected_at"])


def downgrade() -> None:
    op.drop_index("ix_anomaly_signals_detected_at", table_name="anomaly_signals")
    op.drop_index("ix_anomaly_signals_severity", table_name="anomaly_signals")
    op.drop_index("ix_anomaly_signals_anomaly_type", table_name="anomaly_signals")
    op.drop_index("ix_anomaly_signals_purchase_order_id", table_name="anomaly_signals")
    op.drop_index("ix_anomaly_signals_invoice_id", table_name="anomaly_signals")
    op.drop_index("ix_anomaly_signals_vendor_id", table_name="anomaly_signals")
    op.drop_table("anomaly_signals")
