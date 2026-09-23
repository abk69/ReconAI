"""Read-only SQL aggregates for the executive dashboard.

Does not run reconciliation, anomaly detection, risk scoring, or Gemini.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.anomaly.enums import AnomalySeverity
from app.db.models import (
    AnomalySignalRecord,
    Document,
    GoodsReceipt,
    Invoice,
    PurchaseOrder,
    ReconciliationException,
    ResolutionAuditEvent,
    ReviewDecision,
    ReviewTask,
    RiskProfileRecord,
)
from app.domain.enums import DocumentStatus, ExceptionSeverity, ExceptionStatus, ReviewStatus
from app.risk.enums import RiskBand
from app.schemas.dashboard import (
    CountMap,
    DashboardActivityItem,
    DashboardExceptionItem,
    DashboardReviewItem,
    DashboardRiskProfileItem,
    DashboardSummaryResponse,
)

_LIST_LIMIT = 8
_ACTIVITY_PER_SOURCE = 8
_ACTIVITY_LIMIT = 12

RECONCILIATION_NOTE = (
    "Counts are persisted reconciliation exceptions. A successful match is not stored "
    "as its own record, so this view does not report a matched total."
)
RISK_NOTE = (
    "Risk scores are deterministic aggregations of anomaly signals and are not fraud probabilities."
)
REVIEW_NOTE = (
    "Human review is the trust boundary before extraction candidates become authoritative "
    "procurement records."
)
DOCUMENT_NOTE = (
    "Counts are persisted document statuses. They are not processing percentages "
    "or financial totals."
)


def _zero_fill(keys: list[str], rows: list[tuple[object, int]]) -> dict[str, int]:
    counts = {key: 0 for key in keys}
    for value, count in rows:
        counts[str(value)] = int(count)
    return counts


def _count_map(session: Session, column: object, keys: list[str]) -> CountMap:
    rows = list(session.execute(select(column, func.count()).group_by(column)).all())
    counts = _zero_fill(keys, [(value, int(count)) for value, count in rows])
    return CountMap(total=sum(counts.values()), counts=counts)


def _status_count(session: Session, model: type, status: str) -> int:
    value = session.scalar(select(func.count()).select_from(model).where(model.status == status))  # type: ignore[attr-defined]
    return int(value or 0)


def _latest_risk_join():
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
    return RiskProfileRecord, latest, and_(
        RiskProfileRecord.entity_type == latest.c.entity_type,
        RiskProfileRecord.entity_id == latest.c.entity_id,
        RiskProfileRecord.score_version == latest.c.score_version,
        RiskProfileRecord.as_of == latest.c.as_of,
    )


def _risk_counts(session: Session) -> tuple[CountMap, int, list[RiskProfileRecord]]:
    model, latest, condition = _latest_risk_join()
    rows = session.execute(
        select(model.risk_band, func.count()).join(latest, condition).group_by(model.risk_band)
    ).all()
    counts = _zero_fill([band.value for band in RiskBand], [(v, int(c)) for v, c in rows])
    high = counts.get(RiskBand.HIGH.value, 0) + counts.get(RiskBand.CRITICAL.value, 0)
    profiles = list(
        session.scalars(
            select(model)
            .join(latest, condition)
            .order_by(model.calculated_at.desc())
            .limit(_LIST_LIMIT)
        ).all()
    )
    return CountMap(total=sum(counts.values()), counts=counts), high, profiles


def _open_exceptions(session: Session) -> list[DashboardExceptionItem]:
    rows = session.execute(
        select(
            ReconciliationException,
            Invoice.invoice_number,
            PurchaseOrder.po_number,
            GoodsReceipt.grn_number,
        )
        .outerjoin(Invoice, ReconciliationException.invoice_id == Invoice.id)
        .outerjoin(PurchaseOrder, ReconciliationException.purchase_order_id == PurchaseOrder.id)
        .outerjoin(GoodsReceipt, ReconciliationException.goods_receipt_id == GoodsReceipt.id)
        .where(
            ReconciliationException.status.in_(
                [ExceptionStatus.OPEN.value, ExceptionStatus.IN_REVIEW.value]
            )
        )
        .order_by(ReconciliationException.created_at.desc())
        .limit(_LIST_LIMIT)
    ).all()
    items: list[DashboardExceptionItem] = []
    for row, invoice_number, po_number, grn_number in rows:
        items.append(
            DashboardExceptionItem(
                id=row.id,
                exception_type=row.exception_type,
                severity=row.severity,
                status=row.status,
                message=row.message,
                invoice_number=invoice_number,
                po_number=po_number,
                grn_number=grn_number,
                created_at=row.created_at,
            )
        )
    return items


def _pending_reviews(session: Session) -> list[DashboardReviewItem]:
    rows = session.execute(
        select(ReviewTask, Document.original_filename)
        .join(Document, ReviewTask.document_id == Document.id)
        .where(ReviewTask.status == ReviewStatus.PENDING.value)
        .order_by(ReviewTask.created_at.desc())
        .limit(_LIST_LIMIT)
    ).all()
    return [
        DashboardReviewItem(
            id=task.id,
            status=task.status,
            priority=task.priority,
            reason=task.reason,
            document_filename=filename,
            created_at=task.created_at,
        )
        for task, filename in rows
    ]


def _activity(session: Session) -> list[DashboardActivityItem]:
    items: list[DashboardActivityItem] = []

    documents = session.scalars(
        select(Document).order_by(Document.created_at.desc()).limit(_ACTIVITY_PER_SOURCE)
    ).all()
    for row in documents:
        items.append(
            DashboardActivityItem(
                kind="document_recorded",
                record_id=row.id,
                occurred_at=row.created_at,
                title=row.original_filename,
                detail=f"Document status {row.status}",
            )
        )

    exceptions = session.scalars(
        select(ReconciliationException)
        .order_by(ReconciliationException.created_at.desc())
        .limit(_ACTIVITY_PER_SOURCE)
    ).all()
    for row in exceptions:
        items.append(
            DashboardActivityItem(
                kind="reconciliation_exception",
                record_id=row.id,
                occurred_at=row.created_at,
                title=row.exception_type,
                detail=row.message[:240],
            )
        )

    decisions = session.scalars(
        select(ReviewDecision).order_by(ReviewDecision.created_at.desc()).limit(_ACTIVITY_PER_SOURCE)
    ).all()
    for row in decisions:
        items.append(
            DashboardActivityItem(
                kind="review_decision",
                record_id=row.id,
                occurred_at=row.created_at,
                title=row.action,
                detail="Human review decision recorded",
            )
        )

    signals = session.scalars(
        select(AnomalySignalRecord)
        .order_by(AnomalySignalRecord.detected_at.desc())
        .limit(_ACTIVITY_PER_SOURCE)
    ).all()
    for row in signals:
        items.append(
            DashboardActivityItem(
                kind="anomaly_signal",
                record_id=row.id,
                occurred_at=row.detected_at,
                title=row.title,
                detail=f"{row.anomaly_type} · {row.severity}",
            )
        )

    profiles = session.scalars(
        select(RiskProfileRecord)
        .order_by(RiskProfileRecord.calculated_at.desc())
        .limit(_ACTIVITY_PER_SOURCE)
    ).all()
    for row in profiles:
        items.append(
            DashboardActivityItem(
                kind="risk_profile",
                record_id=row.id,
                occurred_at=row.calculated_at,
                title=f"{row.entity_type} {row.risk_band}",
                detail=(
                    f"Persisted score {row.score} as of {row.as_of.isoformat()}. "
                    "Not a fraud probability."
                ),
            )
        )

    audits = session.scalars(
        select(ResolutionAuditEvent)
        .order_by(ResolutionAuditEvent.created_at.desc())
        .limit(_ACTIVITY_PER_SOURCE)
    ).all()
    for row in audits:
        items.append(
            DashboardActivityItem(
                kind="resolution_audit",
                record_id=row.id,
                occurred_at=row.created_at,
                title=row.event_type,
                detail=f"Resolution audit event · actor {row.actor_type}",
            )
        )

    def sort_key(item: DashboardActivityItem) -> tuple[datetime, str, UUID]:
        occurred = item.occurred_at
        if occurred.tzinfo is None:
            occurred = occurred.replace(tzinfo=UTC)
        return (occurred, item.kind, item.record_id)

    items.sort(key=sort_key, reverse=True)
    return items[:_ACTIVITY_LIMIT]


def build_dashboard_summary(session: Session) -> DashboardSummaryResponse:
    """Aggregate persisted records for the dashboard. Read-only."""
    risk_profiles, high_or_critical, latest_profiles = _risk_counts(session)
    return DashboardSummaryResponse(
        documents=_count_map(session, Document.status, [item.value for item in DocumentStatus]),
        reconciliation_exceptions=_count_map(
            session,
            ReconciliationException.status,
            [item.value for item in ExceptionStatus],
        ),
        exception_severity=_count_map(
            session,
            ReconciliationException.severity,
            [item.value for item in ExceptionSeverity],
        ),
        open_exception_count=_status_count(
            session, ReconciliationException, ExceptionStatus.OPEN.value
        ),
        in_review_exception_count=_status_count(
            session, ReconciliationException, ExceptionStatus.IN_REVIEW.value
        ),
        open_exceptions=_open_exceptions(session),
        anomaly_signals=_count_map(
            session,
            AnomalySignalRecord.severity,
            [item.value for item in AnomalySeverity],
        ),
        risk_profiles=risk_profiles,
        high_or_critical_risk_count=high_or_critical,
        latest_risk_profiles=[
            DashboardRiskProfileItem(
                id=row.id,
                entity_type=row.entity_type,
                entity_id=row.entity_id,
                score=row.score,
                risk_band=row.risk_band,
                score_version=row.score_version,
                as_of=row.as_of.isoformat(),
                signal_count=row.signal_count,
                calculated_at=row.calculated_at,
            )
            for row in latest_profiles
        ],
        review_tasks=_count_map(session, ReviewTask.status, [item.value for item in ReviewStatus]),
        pending_review_count=_status_count(session, ReviewTask, ReviewStatus.PENDING.value),
        pending_reviews=_pending_reviews(session),
        recent_activity=_activity(session),
        reconciliation_note=RECONCILIATION_NOTE,
        risk_note=RISK_NOTE,
        review_note=REVIEW_NOTE,
        document_note=DOCUMENT_NOTE,
    )
