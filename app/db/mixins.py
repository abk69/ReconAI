"""Shared columns for tenant-owned rows."""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column


class TenantScoped:
    """Nullable tenant key.

    Existing rows stay NULL until an operator assigns them. New rows are
    stamped from the authenticated tenant. NULL is not a tenant.
    """

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
