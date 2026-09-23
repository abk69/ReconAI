"""Transparent risk scoring API (M9.3)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.risk.enums import RiskEntityType
from app.schemas.risk import (
    RiskProfileHistoryResponse,
    RiskProfileListItem,
    RiskProfileListResponse,
    RiskProfileResponse,
)
from app.services.intelligence_read import (
    entity_exists,
    entity_label,
    list_latest_risk_profiles,
    list_risk_history,
    risk_band_counts,
)
from app.services.risk_service import RiskNotFoundError, RiskService

router = APIRouter(prefix="/risk", tags=["risk"])

DbSession = Annotated[Session, Depends(get_db)]


def _to_response(row) -> RiskProfileResponse:
    return RiskProfileResponse.model_validate(row)


@router.get("/profiles", response_model=RiskProfileListResponse)
def list_risk_profiles(
    session: DbSession,
    entity_type: Annotated[RiskEntityType | None, Query()] = None,
    risk_band: Annotated[str | None, Query(max_length=32)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> RiskProfileListResponse:
    """Latest stored profile per entity and score version. Does not calculate."""
    etype = entity_type.value if entity_type is not None else None
    items, total = list_latest_risk_profiles(
        session,
        entity_type=etype,
        risk_band=risk_band,
        limit=limit,
        offset=offset,
    )
    return RiskProfileListResponse(
        items=[RiskProfileListItem.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        counts_by_band=risk_band_counts(session, entity_type=etype),
    )


@router.get("/profiles/{entity_type}/{entity_id}", response_model=RiskProfileHistoryResponse)
def get_stored_risk_profile(
    entity_type: RiskEntityType,
    entity_id: UUID,
    session: DbSession,
    as_of: Annotated[date | None, Query()] = None,
) -> RiskProfileHistoryResponse:
    """Persisted profiles only. A missing as_of row is an empty current profile."""
    if not entity_exists(session, entity_type.value, entity_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{entity_type.value} {entity_id} was not found.",
        )
    current, history = list_risk_history(
        session,
        entity_type=entity_type.value,
        entity_id=entity_id,
        as_of=as_of,
    )
    return RiskProfileHistoryResponse(
        entity_type=entity_type,
        entity_id=entity_id,
        entity_label=entity_label(session, entity_type.value, entity_id),
        current=_to_response(current) if current is not None else None,
        history=[_to_response(row) for row in history],
    )


@router.get("/vendors/{vendor_id}", response_model=RiskProfileResponse)
def get_vendor_risk(
    vendor_id: UUID,
    session: DbSession,
    as_of: Annotated[date | None, Query()] = None,
) -> RiskProfileResponse:
    service = RiskService(session)
    try:
        row = service.get_or_calculate(
            entity_type=RiskEntityType.VENDOR,
            entity_id=vendor_id,
            as_of=as_of,
        )
    except RiskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row)


@router.get("/invoices/{invoice_id}", response_model=RiskProfileResponse)
def get_invoice_risk(
    invoice_id: UUID,
    session: DbSession,
    as_of: Annotated[date | None, Query()] = None,
) -> RiskProfileResponse:
    service = RiskService(session)
    try:
        row = service.get_or_calculate(
            entity_type=RiskEntityType.INVOICE,
            entity_id=invoice_id,
            as_of=as_of,
        )
    except RiskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row)


@router.get(
    "/purchase-orders/{purchase_order_id}",
    response_model=RiskProfileResponse,
)
def get_po_risk(
    purchase_order_id: UUID,
    session: DbSession,
    as_of: Annotated[date | None, Query()] = None,
) -> RiskProfileResponse:
    service = RiskService(session)
    try:
        row = service.get_or_calculate(
            entity_type=RiskEntityType.PURCHASE_ORDER,
            entity_id=purchase_order_id,
            as_of=as_of,
        )
    except RiskNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row)
