"""Anomaly detection, batch scan, and analytics API routes (M9.1 / M9.2)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.anomaly.analytics import (
    get_anomaly_summary,
    get_anomaly_trends,
    get_vendor_anomaly_summary,
)
from app.anomaly.enums import (
    AnomalyScanStatus,
    AnomalyScanType,
    AnomalySeverity,
    AnomalyTrendPeriod,
    AnomalyType,
)
from app.anomaly.pagination import AnomalyCursorError
from app.anomaly.scanner import (
    AnomalyScanConflictError,
    AnomalyScanError,
    AnomalyScanNotFoundError,
    AnomalyScanService,
)
from app.db.models import Vendor
from app.db.session import get_db
from app.schemas.anomaly import (
    AnomalyDetectResponse,
    AnomalyPageResponse,
    AnomalyScanCreateRequest,
    AnomalyScanCreateResponse,
    AnomalyScanListResponse,
    AnomalyScanResponse,
    AnomalySignalResponse,
    AnomalySummaryResponse,
    AnomalyTrendPoint,
    AnomalyTrendsResponse,
    RiskSignalSummary,
    VendorAnomalySummaryResponse,
)
from app.services.anomaly_service import AnomalyNotFoundError, AnomalyService
from app.services.intelligence_read import list_scan_jobs

router = APIRouter(prefix="/anomalies", tags=["anomalies"])

DbSession = Annotated[Session, Depends(get_db)]


def _to_response(row) -> AnomalySignalResponse:
    return AnomalySignalResponse.model_validate(row)


def _scan_response(job) -> AnomalyScanResponse:
    return AnomalyScanResponse.model_validate(job)


# --- M9.2 scans (before /{anomaly_id}) ---


@router.post(
    "/scans",
    response_model=AnomalyScanCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_anomaly_scan(
    body: AnomalyScanCreateRequest, session: DbSession
) -> AnomalyScanCreateResponse:
    """Create a scan job (PENDING). Does not run the scan in-request."""
    service = AnomalyScanService(session)
    try:
        job, reused = service.create_scan(scan_type=body.scan_type, scan_key=body.scan_key)
        return AnomalyScanCreateResponse(
            scan_id=job.id, status=job.status, reused_existing=reused
        )
    except AnomalyScanError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.get("/scans", response_model=AnomalyScanListResponse)
def list_anomaly_scans(
    session: DbSession,
    scan_status: Annotated[AnomalyScanStatus | None, Query(alias="status")] = None,
    scan_type: Annotated[AnomalyScanType | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AnomalyScanListResponse:
    """Persisted scan jobs. Does not create or run a scan."""
    rows, total = list_scan_jobs(
        session,
        status=scan_status.value if scan_status is not None else None,
        scan_type=scan_type.value if scan_type is not None else None,
        limit=limit,
        offset=offset,
    )
    return AnomalyScanListResponse(
        items=[_scan_response(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/scans/{scan_id}", response_model=AnomalyScanResponse)
def get_anomaly_scan(scan_id: UUID, session: DbSession) -> AnomalyScanResponse:
    service = AnomalyScanService(session)
    try:
        return _scan_response(service.get_scan(scan_id))
    except AnomalyScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post("/scans/{scan_id}/run", response_model=AnomalyScanResponse)
def run_anomaly_scan(scan_id: UUID, session: DbSession) -> AnomalyScanResponse:
    """Explicitly execute a PENDING/resumed scan (service-level path; no Celery)."""
    service = AnomalyScanService(session)
    try:
        return _scan_response(service.run_scan(scan_id))
    except AnomalyScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnomalyScanConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/scans/{scan_id}/resume", response_model=AnomalyScanResponse)
def resume_anomaly_scan(scan_id: UUID, session: DbSession) -> AnomalyScanResponse:
    service = AnomalyScanService(session)
    try:
        return _scan_response(service.resume_scan(scan_id))
    except AnomalyScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnomalyScanConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/scans/{scan_id}/cancel", response_model=AnomalyScanResponse)
def cancel_anomaly_scan(scan_id: UUID, session: DbSession) -> AnomalyScanResponse:
    service = AnomalyScanService(session)
    try:
        return _scan_response(service.cancel_scan(scan_id))
    except AnomalyScanNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except AnomalyScanConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


# --- M9.2 analytics ---


@router.get("/summary", response_model=AnomalySummaryResponse)
def anomaly_summary(
    session: DbSession,
    vendor_id: Annotated[UUID | None, Query()] = None,
    anomaly_type: Annotated[AnomalyType | None, Query()] = None,
    severity: Annotated[AnomalySeverity | None, Query()] = None,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> AnomalySummaryResponse:
    data = get_anomaly_summary(
        session,
        vendor_id=vendor_id,
        anomaly_type=anomaly_type,
        severity=severity,
        start_date=start_date,
        end_date=end_date,
    )
    return AnomalySummaryResponse(
        total_signals=data["total_signals"],
        counts_by_type=data["counts_by_type"],
        counts_by_severity=data["counts_by_severity"],
        counts_by_date=data["counts_by_date"],
        unique_affected_vendors=data["unique_affected_vendors"],
        unique_affected_invoices=data["unique_affected_invoices"],
        unique_affected_pos=data["unique_affected_pos"],
        risk_signal_summary=RiskSignalSummary(**data["risk_signal_summary"]),
    )


@router.get("/trends", response_model=AnomalyTrendsResponse)
def anomaly_trends(
    session: DbSession,
    period: Annotated[AnomalyTrendPeriod, Query()] = AnomalyTrendPeriod.DAILY,
    start_date: Annotated[date | None, Query()] = None,
    end_date: Annotated[date | None, Query()] = None,
) -> AnomalyTrendsResponse:
    try:
        points = get_anomaly_trends(
            session, period=period, start_date=start_date, end_date=end_date
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return AnomalyTrendsResponse(
        period=period,
        points=[AnomalyTrendPoint(**p) for p in points],
    )


@router.get(
    "/vendors/{vendor_id}/summary",
    response_model=VendorAnomalySummaryResponse,
)
def vendor_anomaly_summary(
    vendor_id: UUID, session: DbSession
) -> VendorAnomalySummaryResponse:
    if session.get(Vendor, vendor_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vendor {vendor_id} not found",
        )
    data = get_vendor_anomaly_summary(session, vendor_id)
    return VendorAnomalySummaryResponse(
        vendor_id=vendor_id,
        profile_kind=data["profile_kind"],
        total_anomalies=data["total_anomalies"],
        anomalies_by_type=data["anomalies_by_type"],
        anomalies_by_severity=data["anomalies_by_severity"],
        recent_anomaly_count=data["recent_anomaly_count"],
        recent_window_days=data["recent_window_days"],
        affected_invoice_count=data["affected_invoice_count"],
        affected_po_count=data["affected_po_count"],
        repeated_mismatch_rate=data["repeated_mismatch_rate"],
        risk_signal_summary=RiskSignalSummary(**data["risk_signal_summary"]),
    )


# --- M9.1 detect ---


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


@router.get("", response_model=AnomalyPageResponse)
def list_anomalies(
    session: DbSession,
    anomaly_type: Annotated[AnomalyType | None, Query()] = None,
    severity: Annotated[AnomalySeverity | None, Query()] = None,
    vendor_id: Annotated[UUID | None, Query()] = None,
    invoice_id: Annotated[UUID | None, Query()] = None,
    purchase_order_id: Annotated[UUID | None, Query()] = None,
    detected_from: Annotated[datetime | None, Query()] = None,
    detected_to: Annotated[datetime | None, Query()] = None,
    high_or_critical: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    cursor: Annotated[str | None, Query()] = None,
) -> AnomalyPageResponse:
    """Cursor-paginated anomaly list (detected_at DESC, id DESC)."""
    service = AnomalyService(session)
    try:
        rows, next_cursor = service.list_anomalies_page(
            anomaly_type=anomaly_type,
            severity=severity,
            vendor_id=vendor_id,
            invoice_id=invoice_id,
            purchase_order_id=purchase_order_id,
            detected_from=detected_from,
            detected_to=detected_to,
            high_or_critical=high_or_critical and severity is None,
            limit=limit,
            cursor=cursor,
        )
    except AnomalyCursorError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc
    return AnomalyPageResponse(
        items=[_to_response(r) for r in rows],
        next_cursor=next_cursor,
        limit=limit,
    )


@router.get("/{anomaly_id}", response_model=AnomalySignalResponse)
def get_anomaly(anomaly_id: UUID, session: DbSession) -> AnomalySignalResponse:
    service = AnomalyService(session)
    try:
        row = service.get_anomaly(anomaly_id)
    except AnomalyNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row)
