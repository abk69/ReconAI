"""Add tenants, sessions, and durable processing jobs.

Revision ID: 0019_identity_and_jobs
Revises: 0018_risk_profiles
Create Date: 2026-10-22

Existing business rows keep a NULL tenant_id until an operator assigns them.
Nothing in this migration copies rows onto a tenant.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_identity_and_jobs"
down_revision: str | Sequence[str] | None = "0018_risk_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT_TABLES = (
    "vendors",
    "purchase_orders",
    "purchase_order_lines",
    "goods_receipts",
    "goods_receipt_lines",
    "invoices",
    "invoice_lines",
    "reconciliation_exceptions",
    "documents",
    "document_extraction_results",
    "llm_extraction_results",
    "review_tasks",
    "review_decisions",
    "policy_documents",
    "policy_versions",
    "policy_chunks",
    "policy_grounding_results",
    "resolution_plans",
    "resolution_planning_attempts",
    "proposed_actions",
    "action_approvals",
    "action_executions",
    "resolution_audit_events",
    "anomaly_signals",
    "anomaly_scan_jobs",
    "risk_profiles",
    "exception_review_routes",
    "vendor_clarification_requests",
    "missing_document_requests",
    "manager_escalations",
)

_UNIQUE_RETARGETS = (
    (
        "purchase_orders",
        "uq_purchase_orders_po_number",
        "uq_purchase_orders_tenant_po_number",
        ["tenant_id", "po_number"],
    ),
    (
        "goods_receipts",
        "uq_goods_receipts_grn_number",
        "uq_goods_receipts_tenant_grn_number",
        ["tenant_id", "grn_number"],
    ),
    (
        "invoices",
        "uq_invoices_invoice_number",
        "uq_invoices_tenant_invoice_number",
        ["tenant_id", "invoice_number"],
    ),
    ("documents", "uq_documents_sha256", "uq_documents_tenant_sha256", ["tenant_id", "sha256"]),
    (
        "policy_documents",
        "uq_policy_documents_name",
        "uq_policy_documents_tenant_name",
        ["tenant_id", "name"],
    ),
    (
        "resolution_plans",
        "uq_resolution_plans_planning_key",
        "uq_resolution_plans_tenant_planning_key",
        ["tenant_id", "planning_key"],
    ),
    (
        "anomaly_signals",
        "uq_anomaly_signals_fingerprint",
        "uq_anomaly_signals_tenant_fingerprint",
        ["tenant_id", "fingerprint"],
    ),
    (
        "anomaly_scan_jobs",
        "uq_anomaly_scan_jobs_type_key",
        "uq_anomaly_scan_jobs_tenant_type_key",
        ["tenant_id", "scan_type", "scan_key"],
    ),
    (
        "risk_profiles",
        "uq_risk_profiles_fingerprint",
        "uq_risk_profiles_tenant_fingerprint",
        ["tenant_id", "fingerprint"],
    ),
    (
        "risk_profiles",
        "uq_risk_profiles_entity_version_as_of",
        "uq_risk_profiles_tenant_entity_version_as_of",
        ["tenant_id", "entity_type", "entity_id", "score_version", "as_of"],
    ),
)


def upgrade() -> None:
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_memberships_user_tenant"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_attempts_email_hash", "login_attempts", ["email_hash"])
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=True),
        sa.Column("job_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leased_by", sa.String(length=64), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_category", sa.String(length=32), nullable=True),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.String(length=180), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_processing_jobs_claim", "processing_jobs", ["status", "run_after"])
    op.create_index(
        "ix_processing_jobs_resource", "processing_jobs", ["resource_type", "resource_id"]
    )
    op.create_index("ix_processing_jobs_tenant_id", "processing_jobs", ["tenant_id"])

    for table in _TENANT_TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("tenant_id", sa.Uuid(), nullable=True))
            batch.create_index(f"ix_{table}_tenant_id", ["tenant_id"])
            batch.create_foreign_key(f"fk_{table}_tenant_id", "tenants", ["tenant_id"], ["id"])

    _retarget_vendor_tax_id()
    for table, old, new, columns in _UNIQUE_RETARGETS:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(old, type_="unique")
            batch.create_unique_constraint(new, columns)


def _retarget_vendor_tax_id() -> None:
    bind = op.get_bind()
    uniques = sa.inspect(bind).get_unique_constraints("vendors")
    old = next((item["name"] for item in uniques if item.get("column_names") == ["tax_id"]), None)
    with op.batch_alter_table("vendors") as batch:
        if old:
            batch.drop_constraint(old, type_="unique")
        batch.create_unique_constraint("uq_vendors_tenant_tax_id", ["tenant_id", "tax_id"])


_UNIQUE_RESTORE = (
    (
        "purchase_orders",
        "uq_purchase_orders_tenant_po_number",
        "uq_purchase_orders_po_number",
        ["po_number"],
    ),
    (
        "goods_receipts",
        "uq_goods_receipts_tenant_grn_number",
        "uq_goods_receipts_grn_number",
        ["grn_number"],
    ),
    (
        "invoices",
        "uq_invoices_tenant_invoice_number",
        "uq_invoices_invoice_number",
        ["invoice_number"],
    ),
    ("documents", "uq_documents_tenant_sha256", "uq_documents_sha256", ["sha256"]),
    ("policy_documents", "uq_policy_documents_tenant_name", "uq_policy_documents_name", ["name"]),
    (
        "resolution_plans",
        "uq_resolution_plans_tenant_planning_key",
        "uq_resolution_plans_planning_key",
        ["planning_key"],
    ),
    (
        "anomaly_signals",
        "uq_anomaly_signals_tenant_fingerprint",
        "uq_anomaly_signals_fingerprint",
        ["fingerprint"],
    ),
    (
        "anomaly_scan_jobs",
        "uq_anomaly_scan_jobs_tenant_type_key",
        "uq_anomaly_scan_jobs_type_key",
        ["scan_type", "scan_key"],
    ),
    (
        "risk_profiles",
        "uq_risk_profiles_tenant_fingerprint",
        "uq_risk_profiles_fingerprint",
        ["fingerprint"],
    ),
    (
        "risk_profiles",
        "uq_risk_profiles_tenant_entity_version_as_of",
        "uq_risk_profiles_entity_version_as_of",
        ["entity_type", "entity_id", "score_version", "as_of"],
    ),
)


def downgrade() -> None:
    for table, new, old, columns in _UNIQUE_RESTORE:
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(new, type_="unique")
            batch.create_unique_constraint(old, columns)
    with op.batch_alter_table("vendors") as batch:
        batch.drop_constraint("uq_vendors_tenant_tax_id", type_="unique")
        batch.create_unique_constraint("vendors_tax_id_key", ["tax_id"])
    for table in reversed(_TENANT_TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f"fk_{table}_tenant_id", type_="foreignkey")
            batch.drop_index(f"ix_{table}_tenant_id")
            batch.drop_column("tenant_id")
    op.drop_index("ix_processing_jobs_tenant_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_resource", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_claim", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index("ix_login_attempts_email_hash", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_table("user_sessions")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("tenants")
