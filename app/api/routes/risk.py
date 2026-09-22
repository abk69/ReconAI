"""Transparent risk scoring API (M9.3)."""

from __future__ import annotations

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.risk.enums import RiskEntityType
from app.schemas.risk import RiskProfileResponse
from app.services.risk_service import RiskNotFoundError, RiskService

router = APIRouter(prefix="/risk", tags=["risk"])

DbSession = Annotated[Session, Depends(get_db)]


def _to_response(row) -> RiskProfileResponse:
    return RiskProfileResponse.model_validate(row)


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
