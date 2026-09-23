"""Anomaly detection persistence and orchestration service (M9.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from app.anomaly.contracts import AnomalyConfig, AnomalySignal
from app.anomaly.engine import AnomalyEngine
from app.anomaly.enums import AnomalySeverity, AnomalyType
from app.core.config import Settings, get_settings
from app.db.models import (
    AnomalySignalRecord,
    GoodsReceipt,
    Invoice,
    PurchaseOrder,
    ReconciliationException,
    Vendor,
)
from app.reconciliation.rules import normalize_invoice_number


class AnomalyNotFoundError(Exception):
    """Requested anomaly or related entity was not found."""


class AnomalyServiceError(Exception):
    """Anomaly service validation / domain error."""


def config_from_settings(settings: Settings | None = None) -> AnomalyConfig:
    """Build AnomalyConfig from application Settings (Decimal-safe strings)."""
    s = settings or get_settings()
    return AnomalyConfig(
        price_low_pct=Decimal(s.anomaly_price_low_pct),
        price_medium_pct=Decimal(s.anomaly_price_medium_pct),
        price_high_pct=Decimal(s.anomaly_price_high_pct),
        price_critical_pct=Decimal(s.anomaly_price_critical_pct),
        quantity_low_pct=Decimal(s.anomaly_quantity_low_pct),
        quantity_medium_pct=Decimal(s.anomaly_quantity_medium_pct),
        quantity_high_pct=Decimal(s.anomaly_quantity_high_pct),
        quantity_critical_pct=Decimal(s.anomaly_quantity_critical_pct),
        vendor_spike_min_history=s.vendor_spike_min_history,
        vendor_spike_medium_ratio=Decimal(s.vendor_spike_medium_ratio),
        vendor_spike_high_ratio=Decimal(s.vendor_spike_high_ratio),
        vendor_spike_critical_ratio=Decimal(s.vendor_spike_critical_ratio),
        repeated_mismatch_min_history=s.repeated_mismatch_min_history,
        repeated_mismatch_medium_rate=Decimal(s.repeated_mismatch_medium_rate),
        repeated_mismatch_high_rate=Decimal(s.repeated_mismatch_high_rate),
        repeated_mismatch_critical_rate=Decimal(s.repeated_mismatch_critical_rate),
        repeated_mismatch_window_days=s.repeated_mismatch_window_days,
        timing_long_delay_days=s.timing_long_delay_days,
    )


class AnomalyService:
    """Run deterministic rules, persist signals idempotently, query signals."""

    def __init__(
        self,
        session: Session,
        *,
        config: AnomalyConfig | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._config = config or config_from_settings(settings)
        self._engine = AnomalyEngine(self._config)

    def detect_for_invoice(
        self, invoice_id: UUID, *, commit: bool = True
    ) -> list[AnomalySignalRecord]:
        invoice = self._load_invoice(invoice_id)
        po = self._load_po(invoice.purchase_order_id) if invoice.purchase_order_id else None
        grns = self._load_grns(invoice.purchase_order_id) if invoice.purchase_order_id else []
        siblings = self._load_vendor_invoices(invoice.vendor_id)
        priors = [inv for inv in siblings if inv.id != invoice.id]
        signals = self._engine.detect_for_invoice(
            invoice=invoice,
            purchase_order=po,
            goods_receipts=grns,
            sibling_invoices=siblings,
            prior_vendor_invoices=priors,
        )
        return self._persist_signals(signals, commit=commit)

    def detect_for_vendor(
        self, vendor_id: UUID, *, commit: bool = True
    ) -> list[AnomalySignalRecord]:
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None:
            raise AnomalyNotFoundError(f"Vendor {vendor_id} not found")
        invoices = self._load_vendor_invoices(vendor_id)
        window_days = self._config.repeated_mismatch_window_days
        as_of = date.today()
        window_start = as_of - timedelta(days=window_days)
        window_invoices = [inv for inv in invoices if inv.invoice_date >= window_start]
        inv_ids = [inv.id for inv in window_invoices]
        exception_count = 0
        if inv_ids:
            exception_count = int(
                self._session.scalar(
                    select(func.count())
                    .select_from(ReconciliationException)
                    .where(ReconciliationException.invoice_id.in_(inv_ids))
                )
                or 0
            )
        signals = self._engine.detect_for_vendor(
            vendor_id=vendor_id,
            invoices=invoices,
            invoice_count=len(window_invoices),
            exception_count=exception_count,
            as_of=as_of,
        )
        return self._persist_signals(signals, commit=commit)

    def detect_for_exception(
        self, exception_id: UUID, *, commit: bool = True
    ) -> list[AnomalySignalRecord]:
        exc = self._session.get(ReconciliationException, exception_id)
        if exc is None:
            raise AnomalyNotFoundError(f"ReconciliationException {exception_id} not found")
        invoice = self._load_invoice(exc.invoice_id) if exc.invoice_id else None
        po_id = exc.purchase_order_id or (invoice.purchase_order_id if invoice else None)
        po = self._load_po(po_id) if po_id else None
        grns = self._load_grns(po_id) if po_id else []
        vendor_id = None
        if invoice is not None:
            vendor_id = invoice.vendor_id
        elif po is not None:
            vendor_id = po.vendor_id
        siblings: list[Invoice] = []
        priors: list[Invoice] = []
        invoice_count = 0
        exception_count = 0
        as_of = date.today()
        if vendor_id is not None:
            siblings = self._load_vendor_invoices(vendor_id)
            priors = [inv for inv in siblings if invoice is None or inv.id != invoice.id]
            window_start = as_of - timedelta(days=self._config.repeated_mismatch_window_days)
            window_invoices = [inv for inv in siblings if inv.invoice_date >= window_start]
            invoice_count = len(window_invoices)
            inv_ids = [inv.id for inv in window_invoices]
            if inv_ids:
                exception_count = int(
                    self._session.scalar(
                        select(func.count())
                        .select_from(ReconciliationException)
                        .where(ReconciliationException.invoice_id.in_(inv_ids))
                    )
                    or 0
                )
        signals = self._engine.detect_for_exception(
            invoice=invoice,
            purchase_order=po,
            goods_receipts=grns,
            sibling_invoices=siblings,
            prior_vendor_invoices=priors,
            vendor_id=vendor_id,
            invoice_count=invoice_count,
            exception_count=exception_count,
            as_of=as_of,
        )
        return self._persist_signals(signals, commit=commit)

    def get_anomaly(self, anomaly_id: UUID) -> AnomalySignalRecord:
        row = self._session.get(AnomalySignalRecord, anomaly_id)
        if row is None:
            raise AnomalyNotFoundError(f"AnomalySignal {anomaly_id} not found")
        return row

    def list_anomalies(
        self,
        *,
        anomaly_type: AnomalyType | str | None = None,
        severity: AnomalySeverity | str | None = None,
        vendor_id: UUID | None = None,
        invoice_id: UUID | None = None,
        purchase_order_id: UUID | None = None,
        detected_from: datetime | None = None,
        detected_to: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AnomalySignalRecord]:
        """Offset list (M9.1 compat). Prefer ``list_anomalies_page`` for keyset pagination."""
        stmt: Select[tuple[AnomalySignalRecord]] = select(AnomalySignalRecord)
        if anomaly_type is not None:
            stmt = stmt.where(
                AnomalySignalRecord.anomaly_type
                == (anomaly_type.value if isinstance(anomaly_type, AnomalyType) else anomaly_type)
            )
        if severity is not None:
            stmt = stmt.where(
                AnomalySignalRecord.severity
                == (severity.value if isinstance(severity, AnomalySeverity) else severity)
            )
        if vendor_id is not None:
            stmt = stmt.where(AnomalySignalRecord.vendor_id == vendor_id)
        if invoice_id is not None:
            stmt = stmt.where(AnomalySignalRecord.invoice_id == invoice_id)
        if purchase_order_id is not None:
            stmt = stmt.where(AnomalySignalRecord.purchase_order_id == purchase_order_id)
        if detected_from is not None:
            stmt = stmt.where(AnomalySignalRecord.detected_at >= detected_from)
        if detected_to is not None:
            stmt = stmt.where(AnomalySignalRecord.detected_at <= detected_to)
        stmt = (
            stmt.order_by(
                AnomalySignalRecord.detected_at.desc(),
                AnomalySignalRecord.id.desc(),
            )
            .limit(min(max(limit, 1), 500))
            .offset(max(offset, 0))
        )
        return list(self._session.scalars(stmt).all())

    def list_anomalies_page(
        self,
        *,
        anomaly_type: AnomalyType | str | None = None,
        severity: AnomalySeverity | str | None = None,
        vendor_id: UUID | None = None,
        invoice_id: UUID | None = None,
        purchase_order_id: UUID | None = None,
        detected_from: datetime | None = None,
        detected_to: datetime | None = None,
        high_or_critical: bool = False,
        limit: int = 100,
        cursor: str | None = None,
    ) -> tuple[list[AnomalySignalRecord], str | None]:
        """Keyset pagination on ``(detected_at DESC, id DESC)`` → ``(rows, next_cursor)``."""
        from app.anomaly.pagination import decode_anomaly_cursor, encode_anomaly_cursor

        stmt: Select[tuple[AnomalySignalRecord]] = select(AnomalySignalRecord)
        if anomaly_type is not None:
            stmt = stmt.where(
                AnomalySignalRecord.anomaly_type
                == (anomaly_type.value if isinstance(anomaly_type, AnomalyType) else anomaly_type)
            )
        if severity is not None:
            stmt = stmt.where(
                AnomalySignalRecord.severity
                == (severity.value if isinstance(severity, AnomalySeverity) else severity)
            )
        elif high_or_critical:
            stmt = stmt.where(AnomalySignalRecord.severity.in_(("HIGH", "CRITICAL")))
        if vendor_id is not None:
            stmt = stmt.where(AnomalySignalRecord.vendor_id == vendor_id)
        if invoice_id is not None:
            stmt = stmt.where(AnomalySignalRecord.invoice_id == invoice_id)
        if purchase_order_id is not None:
            stmt = stmt.where(AnomalySignalRecord.purchase_order_id == purchase_order_id)
        if detected_from is not None:
            stmt = stmt.where(AnomalySignalRecord.detected_at >= detected_from)
        if detected_to is not None:
            stmt = stmt.where(AnomalySignalRecord.detected_at <= detected_to)
        if cursor:
            detected_at, anomaly_id = decode_anomaly_cursor(cursor)
            stmt = stmt.where(
                (AnomalySignalRecord.detected_at < detected_at)
                | (
                    (AnomalySignalRecord.detected_at == detected_at)
                    & (AnomalySignalRecord.id < anomaly_id)
                )
            )
        page_size = min(max(limit, 1), 500)
        stmt = stmt.order_by(
            AnomalySignalRecord.detected_at.desc(),
            AnomalySignalRecord.id.desc(),
        ).limit(page_size + 1)
        rows = list(self._session.scalars(stmt).all())
        next_cursor = None
        if len(rows) > page_size:
            rows = rows[:page_size]
            last = rows[-1]
            next_cursor = encode_anomaly_cursor(
                detected_at=last.detected_at, anomaly_id=last.id
            )
        return rows, next_cursor

    def _persist_signals(
        self, signals: list[AnomalySignal], *, commit: bool
    ) -> list[AnomalySignalRecord]:
        rows: list[AnomalySignalRecord] = []
        for signal in signals:
            existing = self._session.scalar(
                select(AnomalySignalRecord).where(
                    AnomalySignalRecord.fingerprint == signal.fingerprint
                )
            )
            if existing is not None:
                rows.append(existing)
                continue
            row = AnomalySignalRecord(
                anomaly_type=signal.anomaly_type.value,
                severity=signal.severity.value,
                score=signal.score,
                vendor_id=signal.vendor_id,
                purchase_order_id=signal.purchase_order_id,
                invoice_id=signal.invoice_id,
                grn_id=signal.grn_id,
                title=signal.title,
                explanation=signal.explanation,
                evidence=dict(signal.evidence),
                fingerprint=signal.fingerprint,
                detected_at=signal.detected_at
                if signal.detected_at.tzinfo
                else signal.detected_at.replace(tzinfo=UTC),
            )
            self._session.add(row)
            rows.append(row)
        self._session.flush()
        if commit:
            self._session.commit()
            for row in rows:
                self._session.refresh(row)
        return rows

    def _load_invoice(self, invoice_id: UUID) -> Invoice:
        invoice = self._session.scalar(
            select(Invoice)
            .where(Invoice.id == invoice_id)
            .options(selectinload(Invoice.lines))
        )
        if invoice is None:
            raise AnomalyNotFoundError(f"Invoice {invoice_id} not found")
        return invoice

    def _load_po(self, po_id: UUID) -> PurchaseOrder:
        po = self._session.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po_id)
            .options(selectinload(PurchaseOrder.lines))
        )
        if po is None:
            raise AnomalyNotFoundError(f"PurchaseOrder {po_id} not found")
        return po

    def _load_grns(self, po_id: UUID) -> list[GoodsReceipt]:
        return list(
            self._session.scalars(
                select(GoodsReceipt).where(GoodsReceipt.purchase_order_id == po_id)
            ).all()
        )

    def _load_vendor_invoices(self, vendor_id: UUID) -> list[Invoice]:
        return list(
            self._session.scalars(
                select(Invoice)
                .where(Invoice.vendor_id == vendor_id)
                .options(selectinload(Invoice.lines))
                .order_by(Invoice.invoice_date.asc())
            ).all()
        )


# Re-export for tests that assert normalization is reused.
__all__ = [
    "AnomalyNotFoundError",
    "AnomalyService",
    "AnomalyServiceError",
    "config_from_settings",
    "normalize_invoice_number",
]
