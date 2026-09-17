"""Invoice API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.procurement import InvoiceCreateRequest, InvoiceResponse
from app.services.procurement_service import (
    ProcurementNotFoundError,
    ProcurementService,
    ProcurementValidationError,
)

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


@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(invoice_id: UUID, session: DbSession) -> InvoiceResponse:
    try:
        invoice = ProcurementService(session).get_invoice(invoice_id)
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return InvoiceResponse.model_validate(invoice)
