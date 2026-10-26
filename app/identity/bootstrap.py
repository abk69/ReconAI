"""Create the first tenant and administrator. Refuses to run twice.

Set RECONAI_BOOTSTRAP_EMAIL, RECONAI_BOOTSTRAP_PASSWORD, and
RECONAI_BOOTSTRAP_TENANT in the environment, then run:

    python -m app.identity.bootstrap

There is no default password and no public registration.
"""

from __future__ import annotations

import os
import sys

from app.db.session import get_session_factory
from app.identity.service import AuthError, AuthService


def main() -> int:
    email = os.environ.get("RECONAI_BOOTSTRAP_EMAIL", "").strip()
    password = os.environ.get("RECONAI_BOOTSTRAP_PASSWORD", "")
    tenant = os.environ.get("RECONAI_BOOTSTRAP_TENANT", "").strip()
    if not email or not password or not tenant:
        print(
            "Set RECONAI_BOOTSTRAP_EMAIL, RECONAI_BOOTSTRAP_PASSWORD, "
            "and RECONAI_BOOTSTRAP_TENANT.",
            file=sys.stderr,
        )
        return 2
    session = get_session_factory()()
    try:
        tenant_row, user = AuthService(session).bootstrap(
            email=email, password=password, tenant_name=tenant
        )
    except AuthError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        session.close()
    print(f"Bootstrapped tenant {tenant_row.id} admin {user.email}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
