"""FastAPI application entrypoint."""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from app.api.middleware import RequestContextMiddleware
from app.api.routes import (
    anomalies,
    dashboard,
    documents,
    goods_receipts,
    health,
    invoices,
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
        version="0.1.0",
        debug=settings.debug,
    )
    prefix = settings.api_prefix
    origins = [item.strip() for item in settings.cors_origins.split(",") if item.strip()]
    if origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
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
    application.include_router(health.router, prefix=prefix)
    application.include_router(dashboard.router, prefix=prefix)
    application.include_router(reconciliation.router, prefix=prefix)
    application.include_router(documents.router, prefix=prefix)
    application.include_router(review.router, prefix=prefix)
    application.include_router(policies.router, prefix=prefix)
    application.include_router(resolution.router, prefix=prefix)
    application.include_router(anomalies.router, prefix=prefix)
    application.include_router(risk.router, prefix=prefix)
    application.include_router(vendors.router, prefix=prefix)
    application.include_router(purchase_orders.router, prefix=prefix)
    application.include_router(goods_receipts.router, prefix=prefix)
    application.include_router(invoices.router, prefix=prefix)
    return application


app = create_app()
