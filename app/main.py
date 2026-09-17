"""FastAPI application entrypoint."""

from fastapi import FastAPI

from app.api.routes import health, reconciliation
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
    application.include_router(health.router, prefix=settings.api_prefix)
    application.include_router(reconciliation.router, prefix=settings.api_prefix)
    return application


app = create_app()
