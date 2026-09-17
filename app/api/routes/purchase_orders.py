"""Purchase order API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.procurement import PurchaseOrderCreateRequest, PurchaseOrderResponse
from app.services.procurement_service import (
    ProcurementNotFoundError,
    ProcurementService,
    ProcurementServiceError,
)

router = APIRouter(prefix="/purchase-orders", tags=["purchase-orders"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
def create_purchase_order(
    body: PurchaseOrderCreateRequest,
    session: DbSession,
) -> PurchaseOrderResponse:
    service = ProcurementService(session)
    try:
        po = service.create_purchase_order(
            po_number=body.po_number,
            vendor_id=body.vendor_id,
            order_date=body.order_date,
            currency=body.currency,
            status=body.status,
            lines=[line.model_dump() for line in body.lines],
        )
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProcurementServiceError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return PurchaseOrderResponse.model_validate(po)


@router.get("/{purchase_order_id}", response_model=PurchaseOrderResponse)
def get_purchase_order(purchase_order_id: UUID, session: DbSession) -> PurchaseOrderResponse:
    try:
        po = ProcurementService(session).get_purchase_order(purchase_order_id)
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return PurchaseOrderResponse.model_validate(po)
