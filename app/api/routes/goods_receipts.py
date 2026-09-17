"""Goods receipt API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.procurement import GoodsReceiptCreateRequest, GoodsReceiptResponse
from app.services.procurement_service import (
    ProcurementNotFoundError,
    ProcurementService,
    ProcurementValidationError,
)

router = APIRouter(prefix="/goods-receipts", tags=["goods-receipts"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=GoodsReceiptResponse, status_code=status.HTTP_201_CREATED)
def create_goods_receipt(
    body: GoodsReceiptCreateRequest,
    session: DbSession,
) -> GoodsReceiptResponse:
    service = ProcurementService(session)
    try:
        grn = service.create_goods_receipt(
            grn_number=body.grn_number,
            purchase_order_id=body.purchase_order_id,
            receipt_date=body.receipt_date,
            status=body.status,
            lines=[line.model_dump() for line in body.lines],
        )
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProcurementValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return GoodsReceiptResponse.model_validate(grn)


@router.get("/{goods_receipt_id}", response_model=GoodsReceiptResponse)
def get_goods_receipt(goods_receipt_id: UUID, session: DbSession) -> GoodsReceiptResponse:
    try:
        grn = ProcurementService(session).get_goods_receipt(goods_receipt_id)
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return GoodsReceiptResponse.model_validate(grn)
