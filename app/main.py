"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.routes import (
    anomalies,
    documents,
    goods_receipts,
    health,
    invoices,
    policies,
    purchase_orders,
    reconciliation,
    resolution,
    review,
    vendors,
)
from app.core.config import get_settings


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
    application.include_router(health.router, prefix=prefix)
    application.include_router(reconciliation.router, prefix=prefix)
    application.include_router(documents.router, prefix=prefix)
    application.include_router(review.router, prefix=prefix)
    application.include_router(policies.router, prefix=prefix)
    application.include_router(resolution.router, prefix=prefix)
    application.include_router(anomalies.router, prefix=prefix)
    application.include_router(vendors.router, prefix=prefix)
    application.include_router(purchase_orders.router, prefix=prefix)
    application.include_router(goods_receipts.router, prefix=prefix)
    application.include_router(invoices.router, prefix=prefix)
    return application


app = create_app()
