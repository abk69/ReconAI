"""Anomaly detection API routes (M9.1)."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.anomaly.enums import AnomalySeverity, AnomalyType
from app.db.session import get_db
from app.schemas.anomaly import AnomalyDetectResponse, AnomalySignalResponse
from app.services.anomaly_service import AnomalyNotFoundError, AnomalyService

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

DbSession = Annotated[Session, Depends(get_db)]


def _to_response(row) -> AnomalySignalResponse:
    return AnomalySignalResponse.model_validate(row)


@router.post(
    "/detect/invoice/{invoice_id}",
    response_model=AnomalyDetectResponse,
    status_code=status.HTTP_200_OK,
)
def detect_invoice_anomalies(invoice_id: UUID, session: DbSession) -> AnomalyDetectResponse:
    service = AnomalyService(session)
    try:
        rows = service.detect_for_invoice(invoice_id)
    except AnomalyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AnomalyDetectResponse(
        signals=[_to_response(r) for r in rows],
        created_or_reused_count=len(rows),
    )


@router.post(
    "/detect/vendor/{vendor_id}",
    response_model=AnomalyDetectResponse,
    status_code=status.HTTP_200_OK,
)
def detect_vendor_anomalies(vendor_id: UUID, session: DbSession) -> AnomalyDetectResponse:
    service = AnomalyService(session)
    try:
        rows = service.detect_for_vendor(vendor_id)
    except AnomalyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AnomalyDetectResponse(
        signals=[_to_response(r) for r in rows],
        created_or_reused_count=len(rows),
    )


@router.post(
    "/detect/exception/{exception_id}",
    response_model=AnomalyDetectResponse,
    status_code=status.HTTP_200_OK,
)
def detect_exception_anomalies(
    exception_id: UUID, session: DbSession
) -> AnomalyDetectResponse:
    service = AnomalyService(session)
    try:
        rows = service.detect_for_exception(exception_id)
    except AnomalyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return AnomalyDetectResponse(
        signals=[_to_response(r) for r in rows],
        created_or_reused_count=len(rows),
    )


@router.get("/{anomaly_id}", response_model=AnomalySignalResponse)
def get_anomaly(anomaly_id: UUID, session: DbSession) -> AnomalySignalResponse:
    service = AnomalyService(session)
    try:
        row = service.get_anomaly(anomaly_id)
    except AnomalyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row)


@router.get("", response_model=list[AnomalySignalResponse])
def list_anomalies(
    session: DbSession,
    anomaly_type: Annotated[AnomalyType | None, Query()] = None,
    severity: Annotated[AnomalySeverity | None, Query()] = None,
    vendor_id: Annotated[UUID | None, Query()] = None,
    invoice_id: Annotated[UUID | None, Query()] = None,
    purchase_order_id: Annotated[UUID | None, Query()] = None,
    detected_from: Annotated[datetime | None, Query()] = None,
    detected_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AnomalySignalResponse]:
    service = AnomalyService(session)
    rows = service.list_anomalies(
        anomaly_type=anomaly_type,
        severity=severity,
        vendor_id=vendor_id,
        invoice_id=invoice_id,
        purchase_order_id=purchase_order_id,
        detected_from=detected_from,
        detected_to=detected_to,
        limit=limit,
        offset=offset,
    )
    return [_to_response(r) for r in rows]
