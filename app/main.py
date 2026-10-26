"""FastAPI application entrypoint."""

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.api.deps import require_access
from app.api.middleware import RequestContextMiddleware
from app.api.routes import (
    anomalies,
    auth,
    dashboard,
    documents,
    goods_receipts,
    health,
    invoices,
    jobs,
    policies,
    purchase_orders,
    reconciliation,
    resolution,
    review,
    risk,
    vendors,
)
from app.core.config import get_settings
from app.core.observability import log_application_error
from app.core.request_context import REQUEST_ID_HEADER, current_request_id


def create_app() -> FastAPI:
    """Build and configure the FastAPI application."""
    settings = get_settings()
    application = FastAPI(
        title="ReconAI",
        description=(
            "Intelligent procurement reconciliation and exception-resolution platform. "
            "Deterministic reconciliation establishes financial facts; AI assists later."
        ),
        version="1.5.0",
        debug=settings.debug,
    )
    prefix = settings.api_prefix
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-CSRF-Token", REQUEST_ID_HEADER],
            expose_headers=[REQUEST_ID_HEADER],
        )
    application.add_middleware(RequestContextMiddleware)

    @application.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> Response:
        if isinstance(exc, StarletteHTTPException):
            return await http_exception_handler(request, exc)
        if isinstance(exc, RequestValidationError):
            return await request_validation_exception_handler(request, exc)
        log_application_error()
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": current_request_id() or "-",
            },
        )

    guard = [Depends(require_access)]
    application.include_router(health.router, prefix=prefix)
    application.include_router(auth.router, prefix=prefix)
    for module in (
        dashboard,
        reconciliation,
        documents,
        review,
        policies,
        resolution,
        anomalies,
        risk,
        vendors,
        purchase_orders,
        goods_receipts,
        invoices,
        jobs,
    ):
        application.include_router(module.router, prefix=prefix, dependencies=guard)
    return application


app = create_app()
