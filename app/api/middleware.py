"""Request correlation and access logging."""

from __future__ import annotations

from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.observability import log_application_error, log_request
from app.core.request_context import (
    REQUEST_ID_HEADER,
    reset_request_id,
    resolve_request_id,
    set_request_id,
)
from app.db.session import get_session_factory
from app.db.tenant_filter import reset_tenant_id, set_tenant_id
from app.identity.service import SESSION_COOKIE, AuthService


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[no-untyped-def]
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        token = set_request_id(request_id)
        tenant_token = _bind_tenant(request)
        started = perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:  # noqa: BLE001
                log_application_error()
                response = JSONResponse(
                    status_code=500,
                    content={"detail": "Internal server error", "request_id": request_id},
                )
            response.headers[REQUEST_ID_HEADER] = request_id
            log_request(
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=(perf_counter() - started) * 1000.0,
            )
            return response
        finally:
            if tenant_token is not None:
                reset_tenant_id(tenant_token)
            reset_request_id(token)


def _bind_tenant(request: Request):
    """Bind the session tenant before endpoint threads are started.

    A sync dependency runs in a different worker thread from the endpoint, so
    a ContextVar set only inside that dependency is not visible to queries.
    """
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    session = get_session_factory()()
    try:
        principal = AuthService(session).principal_for_token(raw)
    finally:
        session.close()
    if principal is None:
        return None
    request.state.principal = principal
    return set_tenant_id(principal.tenant_id)
