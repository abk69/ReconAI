"""Invoice API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.procurement import InvoiceCreateRequest, InvoiceResponse
from app.schemas.workspace import InvoiceListItem, InvoiceListResponse
from app.services.procurement_service import (
    ProcurementNotFoundError,
    ProcurementService,
    ProcurementValidationError,
)
from app.services.workspace_query import list_invoices

router = APIRouter(prefix="/invoices", tags=["invoices"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
def create_invoice(body: InvoiceCreateRequest, session: DbSession) -> InvoiceResponse:
    service = ProcurementService(session)
    try:
        invoice = service.create_invoice(
            invoice_number=body.invoice_number,
            vendor_id=body.vendor_id,
            invoice_date=body.invoice_date,
            currency=body.currency,
            status=body.status,
            purchase_order_id=body.purchase_order_id,
            subtotal=body.subtotal,
            tax_amount=body.tax_amount,
            total_amount=body.total_amount,
            lines=[line.model_dump() for line in body.lines],
        )
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ProcurementValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    return InvoiceResponse.model_validate(invoice)


@router.get("", response_model=InvoiceListResponse)
def list_invoices_route(
    session: DbSession,
    q: Annotated[str | None, Query(max_length=64)] = None,
    invoice_status: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    vendor_id: UUID | None = None,
    purchase_order_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InvoiceListResponse:
    items, total = list_invoices(
        session,
        q=q,
        status=invoice_status,
        vendor_id=vendor_id,
        purchase_order_id=purchase_order_id,
        limit=limit,
        offset=offset,
    )
    return InvoiceListResponse(
        items=[InvoiceListItem.model_validate(item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: UUID, session: DbSession) -> InvoiceResponse:
    try:
        invoice = ProcurementService(session).get_invoice(invoice_id)
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)
