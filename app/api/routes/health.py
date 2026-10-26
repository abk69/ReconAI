"""Liveness and database readiness."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.observability import log_database_not_ready
from app.db.session import get_db
from app.schemas.common import HealthResponse, ReadinessResponse, WorkerHealthResponse
from app.workers.health import assess_worker

router = APIRouter(tags=["health"])
DbSession = Depends(get_db)


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    """Return service liveness. This does not connect to the database."""
    return HealthResponse(status="ok", service="reconai")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
)
def readiness(session: Session = DbSession) -> ReadinessResponse | JSONResponse:
    """Return ready only after the configured database answers SELECT 1."""
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        log_database_not_ready()
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return ReadinessResponse(status="ready")


@router.get(
    "/health/worker",
    response_model=WorkerHealthResponse,
    responses={503: {"model": WorkerHealthResponse}},
)
def worker_health(session: Session = DbSession) -> WorkerHealthResponse | JSONResponse:
    """Report the newest worker poll. Idle workers stay healthy; a stopped one does not."""
    result = assess_worker(session)
    payload = WorkerHealthResponse(status=result.status, last_poll_at=result.last_poll_at)
    if result.status != "healthy":
        return JSONResponse(status_code=503, content=payload.model_dump(mode="json"))
    return payload
