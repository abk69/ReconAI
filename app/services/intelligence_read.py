"""Read-only risk profile and scan queries. Does not score or scan."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db.models import (
    AnomalyScanJob,
    Invoice,
    PurchaseOrder,
    RiskProfileRecord,
    Vendor,
)
from app.risk.enums import RiskBand, RiskEntityType


def _latest_risk_join():
    """Same latest-profile rule as the executive dashboard: max as_of per entity and version."""
    latest = (
        select(
            RiskProfileRecord.entity_type.label("entity_type"),
            RiskProfileRecord.entity_id.label("entity_id"),
            RiskProfileRecord.score_version.label("score_version"),
            func.max(RiskProfileRecord.as_of).label("as_of"),
        )
        .group_by(
            RiskProfileRecord.entity_type,
            RiskProfileRecord.entity_id,
            RiskProfileRecord.score_version,
        )
        .subquery()
    )
    condition = and_(
        RiskProfileRecord.entity_type == latest.c.entity_type,
        RiskProfileRecord.entity_id == latest.c.entity_id,
        RiskProfileRecord.score_version == latest.c.score_version,
        RiskProfileRecord.as_of == latest.c.as_of,
    )
    return latest, condition


def risk_band_counts(session: Session, *, entity_type: str | None) -> dict[str, int]:
    latest, condition = _latest_risk_join()
    stmt = (
        select(RiskProfileRecord.risk_band, func.count())
        .join(latest, condition)
        .group_by(RiskProfileRecord.risk_band)
    )
    if entity_type:
        stmt = stmt.where(RiskProfileRecord.entity_type == entity_type)
    found = {band: int(count) for band, count in session.execute(stmt).all()}
    return {band.value: found.get(band.value, 0) for band in RiskBand}


def list_latest_risk_profiles(
    session: Session,
    *,
    entity_type: str | None,
    risk_band: str | None,
    limit: int,
    offset: int,
) -> tuple[list[dict[str, object]], int]:
    latest, condition = _latest_risk_join()
    base = select(RiskProfileRecord).join(latest, condition)
    if entity_type:
        base = base.where(RiskProfileRecord.entity_type == entity_type)
    if risk_band:
        base = base.where(RiskProfileRecord.risk_band == risk_band)
    total = int(session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    rows = list(
        session.scalars(
            base.order_by(RiskProfileRecord.calculated_at.desc()).limit(limit).offset(offset)
        ).all()
    )
    labels = _entity_labels(session, rows)
    items = [
        {
            "id": row.id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "entity_label": labels.get((row.entity_type, row.entity_id)),
            "score": row.score,
            "risk_band": row.risk_band,
            "score_version": row.score_version,
            "as_of": row.as_of,
            "calculated_at": row.calculated_at,
            "signal_count": row.signal_count,
        }
        for row in rows
    ]
    return items, total


def entity_exists(session: Session, entity_type: str, entity_id: UUID) -> bool:
    model = {
        RiskEntityType.VENDOR.value: Vendor,
        RiskEntityType.INVOICE.value: Invoice,
        RiskEntityType.PURCHASE_ORDER.value: PurchaseOrder,
    }.get(entity_type)
    if model is None:
        return False
    return session.get(model, entity_id) is not None


def entity_label(session: Session, entity_type: str, entity_id: UUID) -> str | None:
    if entity_type == RiskEntityType.VENDOR.value:
        row = session.get(Vendor, entity_id)
        return row.name if row is not None else None
    if entity_type == RiskEntityType.INVOICE.value:
        row = session.get(Invoice, entity_id)
        return row.invoice_number if row is not None else None
    if entity_type == RiskEntityType.PURCHASE_ORDER.value:
        row = session.get(PurchaseOrder, entity_id)
        return row.po_number if row is not None else None
    return None


def list_risk_history(
    session: Session,
    *,
    entity_type: str,
    entity_id: UUID,
    as_of: date | None,
) -> tuple[RiskProfileRecord | None, list[RiskProfileRecord]]:
    rows = list(
        session.scalars(
            select(RiskProfileRecord)
            .where(
                RiskProfileRecord.entity_type == entity_type,
                RiskProfileRecord.entity_id == entity_id,
            )
            .order_by(RiskProfileRecord.as_of.desc(), RiskProfileRecord.calculated_at.desc())
        ).all()
    )
    if as_of is None:
        current = rows[0] if rows else None
    else:
        current = next((row for row in rows if row.as_of == as_of), None)
    return current, rows


def list_scan_jobs(
    session: Session,
    *,
    status: str | None,
    scan_type: str | None,
    limit: int,
    offset: int,
) -> tuple[list[AnomalyScanJob], int]:
    stmt = select(AnomalyScanJob)
    if status:
        stmt = stmt.where(AnomalyScanJob.status == status)
    if scan_type:
        stmt = stmt.where(AnomalyScanJob.scan_type == scan_type)
    total = int(session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = list(
        session.scalars(
            stmt.order_by(AnomalyScanJob.requested_at.desc()).limit(limit).offset(offset)
        ).all()
    )
    return rows, total


def _entity_labels(
    session: Session, rows: list[RiskProfileRecord]
) -> dict[tuple[str, UUID], str]:
    labels: dict[tuple[str, UUID], str] = {}
    vendor_ids = [row.entity_id for row in rows if row.entity_type == RiskEntityType.VENDOR.value]
    invoice_ids = [row.entity_id for row in rows if row.entity_type == RiskEntityType.INVOICE.value]
    po_ids = [
        row.entity_id for row in rows if row.entity_type == RiskEntityType.PURCHASE_ORDER.value
    ]
    if vendor_ids:
        for row_id, name in session.execute(
            select(Vendor.id, Vendor.name).where(Vendor.id.in_(vendor_ids))
        ):
            labels[(RiskEntityType.VENDOR.value, row_id)] = name
    if invoice_ids:
        for row_id, number in session.execute(
            select(Invoice.id, Invoice.invoice_number).where(Invoice.id.in_(invoice_ids))
        ):
            labels[(RiskEntityType.INVOICE.value, row_id)] = number
    if po_ids:
        for row_id, number in session.execute(
            select(PurchaseOrder.id, PurchaseOrder.po_number).where(PurchaseOrder.id.in_(po_ids))
        ):
            labels[(RiskEntityType.PURCHASE_ORDER.value, row_id)] = number
    return labels
