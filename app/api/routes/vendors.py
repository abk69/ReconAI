"""Vendor API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.procurement import VendorCreateRequest, VendorResponse
from app.services.procurement_service import ProcurementNotFoundError, ProcurementService

router = APIRouter(prefix="/vendors", tags=["vendors"])
DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=VendorResponse, status_code=status.HTTP_201_CREATED)
def create_vendor(body: VendorCreateRequest, session: DbSession) -> VendorResponse:
    vendor = ProcurementService(session).create_vendor(name=body.name, tax_id=body.tax_id)
    return VendorResponse.model_validate(vendor)


@router.get("/{vendor_id}", response_model=VendorResponse)
def get_vendor(vendor_id: UUID, session: DbSession) -> VendorResponse:
    try:
        vendor = ProcurementService(session).get_vendor(vendor_id)
    except ProcurementNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return VendorResponse.model_validate(vendor)
