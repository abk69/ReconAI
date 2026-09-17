"""Add documents table for secure file intake metadata.

Revision ID: 0003_documents
Revises: 0002_exception_fingerprint
Create Date: 2026-09-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_documents"
down_revision: str | Sequence[str] | None = "0002_exception_fingerprint"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=512), nullable=False),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("document_type", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=128), nullable=False),
        sa.Column("file_extension", sa.String(length=16), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_path", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=True),
        sa.Column("purchase_order_id", sa.Uuid(), nullable=True),
        sa.Column("goods_receipt_id", sa.Uuid(), nullable=True),
        sa.Column("invoice_id", sa.Uuid(), nullable=True),
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
        sa.ForeignKeyConstraint(["goods_receipt_id"], ["goods_receipts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["purchase_order_id"], ["purchase_orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256", name="uq_documents_sha256"),
    )
    op.create_index("ix_documents_sha256", "documents", ["sha256"], unique=False)
    op.create_index("ix_documents_document_type", "documents", ["document_type"], unique=False)
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)
    op.create_index(op.f("ix_documents_vendor_id"), "documents", ["vendor_id"], unique=False)
    op.create_index(
        op.f("ix_documents_purchase_order_id"),
        "documents",
        ["purchase_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_documents_goods_receipt_id"),
        "documents",
        ["goods_receipt_id"],
        unique=False,
    )
    op.create_index(op.f("ix_documents_invoice_id"), "documents", ["invoice_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_documents_invoice_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_goods_receipt_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_purchase_order_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_vendor_id"), table_name="documents")
    op.drop_index("ix_documents_status", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_index("ix_documents_sha256", table_name="documents")
    op.drop_table("documents")
