"""Goods receipt API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.procurement import GoodsReceiptCreateRequest, GoodsReceiptResponse
from app.schemas.workspace import GoodsReceiptListItem, GoodsReceiptListResponse
from app.services.procurement_service import (
    ProcurementNotFoundError,
    ProcurementService,
    ProcurementValidationError,
)
from app.services.workspace_query import list_goods_receipts

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


@router.get("", response_model=GoodsReceiptListResponse)
def list_goods_receipts_route(
    session: DbSession,
    q: Annotated[str | None, Query(max_length=64)] = None,
    grn_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    purchase_order_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GoodsReceiptListResponse:
    items, total = list_goods_receipts(
        session,
        q=q,
        status=grn_status,
        purchase_order_id=purchase_order_id,
        limit=limit,
        offset=offset,
    )
    return GoodsReceiptListResponse(
        items=[GoodsReceiptListItem.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{goods_receipt_id}", response_model=GoodsReceiptResponse)
def get_goods_receipt(goods_receipt_id: UUID, session: DbSession) -> GoodsReceiptResponse:
    try:
        grn = ProcurementService(session).get_goods_receipt(goods_receipt_id)
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return GoodsReceiptResponse.model_validate(grn)
