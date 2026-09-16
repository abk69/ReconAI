"""Initial procurement persistence schema.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-16
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Production PostgreSQL uses JSONB; SQLite (isolated tests) uses JSON.
JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("tax_id", sa.String(length=64), nullable=True),
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
        sa.UniqueConstraint("tax_id"),
    )
    op.create_index("ix_vendors_tax_id", "vendors", ["tax_id"], unique=False)

    op.create_table(
        "purchase_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("po_number", sa.String(length=64), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
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
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("po_number", name="uq_purchase_orders_po_number"),
    )
    op.create_index("ix_purchase_orders_po_number", "purchase_orders", ["po_number"], unique=False)
    op.create_index(
        op.f("ix_purchase_orders_vendor_id"), "purchase_orders", ["vendor_id"], unique=False
    )

    op.create_table(
        "purchase_order_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "purchase_order_id", "line_number", name="uq_purchase_order_lines_po_line"
        ),
    )
    op.create_index(
        op.f("ix_purchase_order_lines_purchase_order_id"),
        "purchase_order_lines",
        ["purchase_order_id"],
        unique=False,
    )

    op.create_table(
        "goods_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("grn_number", sa.String(length=64), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=False),
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
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("grn_number", name="uq_goods_receipts_grn_number"),
    )
    op.create_index("ix_goods_receipts_grn_number", "goods_receipts", ["grn_number"], unique=False)
    op.create_index(
        op.f("ix_goods_receipts_purchase_order_id"),
        "goods_receipts",
        ["purchase_order_id"],
        unique=False,
    )

    op.create_table(
        "invoices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_number", sa.String(length=64), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("subtotal", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("tax_amount", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("total_amount", sa.Numeric(precision=18, scale=4), nullable=False),
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
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
    )
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"], unique=False)
    op.create_index(
        op.f("ix_invoices_purchase_order_id"), "invoices", ["purchase_order_id"], unique=False
    )
    op.create_index(op.f("ix_invoices_vendor_id"), "invoices", ["vendor_id"], unique=False)

    op.create_table(
        "goods_receipt_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("received_quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["purchase_order_line_id"], ["purchase_order_lines.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "goods_receipt_id", "line_number", name="uq_goods_receipt_lines_grn_line"
        ),
    )
    op.create_index(
        op.f("ix_goods_receipt_lines_goods_receipt_id"),
        "goods_receipt_lines",
        ["goods_receipt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_goods_receipt_lines_purchase_order_line_id"),
        "goods_receipt_lines",
        ["purchase_order_line_id"],
        unique=False,
    )

    op.create_table(
        "invoice_lines",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invoice_id", sa.Uuid(), nullable=False),
        sa.Column("purchase_order_line_id", sa.Uuid(), nullable=True),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("unit_price", sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column("tax_rate", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["purchase_order_line_id"], ["purchase_order_lines.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("invoice_id", "line_number", name="uq_invoice_lines_invoice_line"),
    )
    op.create_index(
        op.f("ix_invoice_lines_invoice_id"), "invoice_lines", ["invoice_id"], unique=False
    )
    op.create_index(
        op.f("ix_invoice_lines_purchase_order_line_id"),
        "invoice_lines",
        ["purchase_order_line_id"],
        unique=False,
    )

    op.create_table(
        "reconciliation_exceptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exception_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
        sa.Column("source_document_ids", JsonDocument, nullable=False),
        sa.Column("evidence", JsonDocument, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_reconciliation_exceptions_goods_receipt_id"),
        "reconciliation_exceptions",
        ["goods_receipt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_exceptions_invoice_id"),
        "reconciliation_exceptions",
        ["invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_reconciliation_exceptions_purchase_order_id"),
        "reconciliation_exceptions",
        ["purchase_order_id"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_exceptions_status", "reconciliation_exceptions", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_reconciliation_exceptions_status", table_name="reconciliation_exceptions")
    op.drop_index(
        op.f("ix_reconciliation_exceptions_purchase_order_id"),
        table_name="reconciliation_exceptions",
    )
    op.drop_index(
        op.f("ix_reconciliation_exceptions_invoice_id"), table_name="reconciliation_exceptions"
    )
    op.drop_index(
        op.f("ix_reconciliation_exceptions_goods_receipt_id"),
        table_name="reconciliation_exceptions",
    )
    op.drop_table("reconciliation_exceptions")

    op.drop_index(op.f("ix_invoice_lines_purchase_order_line_id"), table_name="invoice_lines")
    op.drop_index(op.f("ix_invoice_lines_invoice_id"), table_name="invoice_lines")
    op.drop_table("invoice_lines")

    op.drop_index(
        op.f("ix_goods_receipt_lines_purchase_order_line_id"), table_name="goods_receipt_lines"
    )
    op.drop_index(op.f("ix_goods_receipt_lines_goods_receipt_id"), table_name="goods_receipt_lines")
    op.drop_table("goods_receipt_lines")

    op.drop_index(op.f("ix_invoices_vendor_id"), table_name="invoices")
    op.drop_index(op.f("ix_invoices_purchase_order_id"), table_name="invoices")
    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.drop_table("invoices")

    op.drop_index(op.f("ix_goods_receipts_purchase_order_id"), table_name="goods_receipts")
    op.drop_index("ix_goods_receipts_grn_number", table_name="goods_receipts")
    op.drop_table("goods_receipts")

    op.drop_index(
        op.f("ix_purchase_order_lines_purchase_order_id"), table_name="purchase_order_lines"
    )
    op.drop_table("purchase_order_lines")

    op.drop_index(op.f("ix_purchase_orders_vendor_id"), table_name="purchase_orders")
    op.drop_index("ix_purchase_orders_po_number", table_name="purchase_orders")
    op.drop_table("purchase_orders")

    op.drop_index("ix_vendors_tax_id", table_name="vendors")
    op.drop_table("vendors")
