"""Deterministic procurement anomaly analytics (M9.2).

Aggregations use SQL — not Python loops over full result sets.
These are risk-signal summaries, not fraud scores or probabilities.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.orm import Session

from app.anomaly.enums import AnomalySeverity, AnomalyTrendPeriod, AnomalyType
from app.db.models import AnomalySignalRecord


def _apply_filters(
    stmt,
    *,
    vendor_id: UUID | None = None,
    anomaly_type: AnomalyType | str | None = None,
    severity: AnomalySeverity | str | None = None,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
):
    if vendor_id is not None:
        stmt = stmt.where(AnomalySignalRecord.vendor_id == vendor_id)
    if anomaly_type is not None:
        val = anomaly_type.value if isinstance(anomaly_type, AnomalyType) else anomaly_type
        stmt = stmt.where(AnomalySignalRecord.anomaly_type == val)
    if severity is not None:
        val = severity.value if isinstance(severity, AnomalySeverity) else severity
        stmt = stmt.where(AnomalySignalRecord.severity == val)
    if start_date is not None:
        start = (
            start_date
            if isinstance(start_date, datetime)
            else datetime.combine(start_date, datetime.min.time()).replace(tzinfo=UTC)
        )
        stmt = stmt.where(AnomalySignalRecord.detected_at >= start)
    if end_date is not None:
        end = (
            end_date
            if isinstance(end_date, datetime)
            else datetime.combine(end_date, datetime.max.time()).replace(tzinfo=UTC)
        )
        stmt = stmt.where(AnomalySignalRecord.detected_at <= end)
    return stmt


def _dialect_name(session: Session) -> str:
    bind = session.get_bind()
    return bind.dialect.name if bind is not None else "sqlite"


def _period_bucket(session: Session, detected_at_col, period: AnomalyTrendPeriod):
    dialect = _dialect_name(session)
    if period is AnomalyTrendPeriod.DAILY:
        return func.date(detected_at_col)
    if period is AnomalyTrendPeriod.WEEKLY:
        if dialect == "postgresql":
            return func.to_char(
                func.date_trunc("week", detected_at_col), 'IYYY-"W"IW'
            )
        return func.strftime("%Y-W%W", detected_at_col)
    # monthly
    if dialect == "postgresql":
        return func.to_char(detected_at_col, "YYYY-MM")
    return func.strftime("%Y-%m", detected_at_col)


def get_anomaly_summary(
    session: Session,
    *,
    vendor_id: UUID | None = None,
    anomaly_type: AnomalyType | str | None = None,
    severity: AnomalySeverity | str | None = None,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
) -> dict[str, Any]:
    """Overall deterministic anomaly summary (counts only — not a fraud score)."""
    base = _apply_filters(
        select(AnomalySignalRecord),
        vendor_id=vendor_id,
        anomaly_type=anomaly_type,
        severity=severity,
        start_date=start_date,
        end_date=end_date,
    )
    subq = base.subquery()

    total = int(session.scalar(select(func.count()).select_from(subq)) or 0)

    by_type_rows = session.execute(
        select(subq.c.anomaly_type, func.count()).group_by(subq.c.anomaly_type)
    ).all()
    by_severity_rows = session.execute(
        select(subq.c.severity, func.count()).group_by(subq.c.severity)
    ).all()

    day_expr = func.date(subq.c.detected_at)
    by_date_rows = session.execute(
        select(day_expr, func.count()).group_by(day_expr).order_by(day_expr.asc())
    ).all()

    vendors = int(
        session.scalar(
            select(func.count(func.distinct(subq.c.vendor_id))).where(
                subq.c.vendor_id.is_not(None)
            )
        )
        or 0
    )
    invoices = int(
        session.scalar(
            select(func.count(func.distinct(subq.c.invoice_id))).where(
                subq.c.invoice_id.is_not(None)
            )
        )
        or 0
    )
    pos = int(
        session.scalar(
            select(func.count(func.distinct(subq.c.purchase_order_id))).where(
                subq.c.purchase_order_id.is_not(None)
            )
        )
        or 0
    )

    sev_map = {r[0]: int(r[1]) for r in by_severity_rows}
    risk = {
        "low_count": sev_map.get(AnomalySeverity.LOW.value, 0),
        "medium_count": sev_map.get(AnomalySeverity.MEDIUM.value, 0),
        "high_count": sev_map.get(AnomalySeverity.HIGH.value, 0),
        "critical_count": sev_map.get(AnomalySeverity.CRITICAL.value, 0),
        "open_signal_count": total,
        "affected_vendor_count": vendors,
        "affected_invoice_count": invoices,
    }

    return {
        "total_signals": total,
        "counts_by_type": {r[0]: int(r[1]) for r in by_type_rows},
        "counts_by_severity": sev_map,
        "counts_by_date": {
            (r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])): int(r[1])
            for r in by_date_rows
            if r[0] is not None
        },
        "unique_affected_vendors": vendors,
        "unique_affected_invoices": invoices,
        "unique_affected_pos": pos,
        "risk_signal_summary": risk,
    }


def get_vendor_anomaly_summary(
    session: Session,
    vendor_id: UUID,
    *,
    recent_days: int = 30,
) -> dict[str, Any]:
    """Vendor anomaly profile / risk-signal profile (not a fraud score)."""
    overall = get_anomaly_summary(session, vendor_id=vendor_id)
    recent_start = datetime.now(UTC) - timedelta(days=recent_days)
    recent = get_anomaly_summary(session, vendor_id=vendor_id, start_date=recent_start)

    repeated = session.scalar(
        select(AnomalySignalRecord)
        .where(
            AnomalySignalRecord.vendor_id == vendor_id,
            AnomalySignalRecord.anomaly_type == AnomalyType.REPEATED_MISMATCH.value,
        )
        .order_by(AnomalySignalRecord.detected_at.desc())
        .limit(1)
    )
    repeated_rate = None
    if repeated is not None and isinstance(repeated.evidence, dict):
        repeated_rate = repeated.evidence.get("exception_rate")

    return {
        "vendor_id": str(vendor_id),
        "profile_kind": "anomaly_profile",
        "total_anomalies": overall["total_signals"],
        "anomalies_by_type": overall["counts_by_type"],
        "anomalies_by_severity": overall["counts_by_severity"],
        "recent_anomaly_count": recent["total_signals"],
        "recent_window_days": recent_days,
        "affected_invoice_count": overall["unique_affected_invoices"],
        "affected_po_count": overall["unique_affected_pos"],
        "repeated_mismatch_rate": repeated_rate,
        "risk_signal_summary": overall["risk_signal_summary"],
    }


def get_anomaly_trends(
    session: Session,
    *,
    period: AnomalyTrendPeriod | str = AnomalyTrendPeriod.DAILY,
    start_date: date | datetime | None = None,
    end_date: date | datetime | None = None,
) -> list[dict[str, Any]]:
    """Deterministic trend buckets. Does not fabricate missing periods."""
    try:
        p = (
            period
            if isinstance(period, AnomalyTrendPeriod)
            else AnomalyTrendPeriod(period)
        )
    except ValueError as exc:
        raise ValueError(
            f"Invalid period {period!r}; allowed: daily, weekly, monthly"
        ) from exc

    filtered = _apply_filters(
        select(AnomalySignalRecord.detected_at, AnomalySignalRecord.severity),
        start_date=start_date,
        end_date=end_date,
    ).subquery()

    bucket = _period_bucket(session, filtered.c.detected_at, p)
    high_crit = func.sum(
        cast(
            filtered.c.severity.in_(
                [AnomalySeverity.HIGH.value, AnomalySeverity.CRITICAL.value]
            ),
            Integer,
        )
    )
    rows = session.execute(
        select(
            bucket.label("period"),
            func.count().label("count"),
            high_crit.label("hc"),
        )
        .group_by(bucket)
        .order_by(bucket.asc())
    ).all()

    return [
        {
            "period": str(r[0]),
            "count": int(r[1]),
            "high_or_critical": int(r[2] or 0),
        }
        for r in rows
        if r[0] is not None
    ]
