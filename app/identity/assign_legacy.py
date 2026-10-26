"""Assign pre-tenant rows to one tenant. This does not run during migration.

Existing rows stay invisible until an operator chooses a tenant:

    RECONAI_ASSIGN_LEGACY=yes RECONAI_ASSIGN_TENANT_ID=<uuid> python -m app.identity.assign_legacy
"""

from __future__ import annotations

import os
import sys
import uuid

from sqlalchemy import update

from app.db.base import Base
from app.db.session import get_session_factory
from app.db.tenant_filter import suspend_tenant_filter


def assign(tenant_id: uuid.UUID) -> int:
    session = get_session_factory()()
    changed = 0
    try:
        with suspend_tenant_filter():
            for mapper in Base.registry.mappers:
                model = mapper.class_
                if "tenant_id" not in mapper.attrs or model.__tablename__ in {
                    "memberships",
                    "user_sessions",
                    "processing_jobs",
                }:
                    continue
                result = session.execute(
                    update(model).where(model.tenant_id.is_(None)).values(tenant_id=tenant_id)
                )
                changed += result.rowcount or 0
            session.commit()
    finally:
        session.close()
    return changed


def main() -> int:
    if os.environ.get("RECONAI_ASSIGN_LEGACY") != "yes":
        print("Refusing to assign legacy rows without RECONAI_ASSIGN_LEGACY=yes.", file=sys.stderr)
        return 2
    raw = os.environ.get("RECONAI_ASSIGN_TENANT_ID", "").strip()
    try:
        tenant_id = uuid.UUID(raw)
    except ValueError:
        print(
            "Set RECONAI_ASSIGN_TENANT_ID to the tenant that should own existing rows.",
            file=sys.stderr,
        )
        return 2
    print(f"Assigned {assign(tenant_id)} legacy rows to {tenant_id}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
