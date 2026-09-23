"""Read-only executive dashboard summary."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import build_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
DbSession = Annotated[Session, Depends(get_db)]


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(session: DbSession) -> DashboardSummaryResponse:
    """Return persisted counts and recent records. Does not mutate data."""
    return build_dashboard_summary(session)
