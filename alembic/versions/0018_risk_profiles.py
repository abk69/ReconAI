"""Add risk_profiles table (M9.3).

Revision ID: 0018_risk_profiles
Revises: 0017_anomaly_scan_jobs
Create Date: 2026-09-22

Immutable deterministic risk profiles derived from anomaly signals.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0018_risk_profiles"
down_revision: str | Sequence[str] | None = "0017_anomaly_scan_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JsonDocument = postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "risk_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("entity_type", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("risk_band", sa.String(length=32), nullable=False),
        sa.Column("score_version", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("breakdown", JsonDocument, nullable=False),
        sa.Column("fingerprint", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("fingerprint", name="uq_risk_profiles_fingerprint"),
        sa.UniqueConstraint(
            "entity_type",
            "entity_id",
            "score_version",
            "as_of",
            name="uq_risk_profiles_entity_version_as_of",
        ),
    )
    op.create_index(
        "ix_risk_profiles_entity", "risk_profiles", ["entity_type", "entity_id"]
    )
    op.create_index("ix_risk_profiles_score_version", "risk_profiles", ["score_version"])
    op.create_index("ix_risk_profiles_calculated_at", "risk_profiles", ["calculated_at"])
    op.create_index("ix_risk_profiles_risk_band", "risk_profiles", ["risk_band"])


def downgrade() -> None:
    op.drop_index("ix_risk_profiles_risk_band", table_name="risk_profiles")
    op.drop_index("ix_risk_profiles_calculated_at", table_name="risk_profiles")
    op.drop_index("ix_risk_profiles_score_version", table_name="risk_profiles")
    op.drop_index("ix_risk_profiles_entity", table_name="risk_profiles")
    op.drop_table("risk_profiles")
