"""Request dependencies for identity and database access."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.tenant_filter import set_tenant_id
from app.identity.access import permission_for
from app.identity.service import SESSION_COOKIE, AuthService, Principal

DbSession = Annotated[Session, Depends(get_db)]
_UNSAFE = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def get_principal(request: Request, session: DbSession) -> Principal:
    cached = getattr(request.state, "principal", None)
    if isinstance(cached, Principal):
        principal = cached
    else:
        raw = request.cookies.get(SESSION_COOKIE)
        if not raw:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required."
            )
        principal = AuthService(session).principal_for_token(raw)
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sign in required.")
    if request.method.upper() in _UNSAFE:
        header = request.headers.get("x-csrf-token", "")
        if not header or header != principal.csrf_token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This action failed the session check.",
            )
    set_tenant_id(principal.tenant_id)
    return principal


CurrentUser = Annotated[Principal, Depends(get_principal)]


def require_access(
    request: Request,
    principal: Annotated[Principal, Depends(get_principal)],
) -> Principal:
    permission = permission_for(request)
    if not principal.allows(permission):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You cannot do that.")
    return principal
