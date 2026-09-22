"""Deterministic anomaly detection rules (M9.1). No LLM / no financial mutation."""


from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.anomaly.contracts import AnomalyConfig, AnomalySignal
from app.anomaly.enums import SEVERITY_SCORE, AnomalySeverity, AnomalyType
from app.anomaly.evidence import (
    decimal_str,
    explain_from_evidence,
    severity_from_percent_thresholds,
    severity_from_rate_thresholds,
    severity_from_ratio_thresholds,
)
from app.anomaly.fingerprints import build_anomaly_fingerprint
from app.reconciliation.rules import normalize_invoice_number, percent_variance


class InvoiceView(Protocol):
    id: UUID
    invoice_number: str
    vendor_id: UUID
    purchase_order_id: UUID | None
    invoice_date: date
    total_amount: Decimal
    lines: list


class PurchaseOrderView(Protocol):
    id: UUID
    vendor_id: UUID
    order_date: date
    lines: list


class GoodsReceiptView(Protocol):
    id: UUID
    purchase_order_id: UUID
    receipt_date: date


def _score(severity: AnomalySeverity) -> Decimal:
    return Decimal(SEVERITY_SCORE[severity])


def _now() -> datetime:
    return datetime.now(UTC)


def _signal(
    *,
    anomaly_type: AnomalyType,
    severity: AnomalySeverity,
    evidence: dict,
    fingerprint: str,
    vendor_id: UUID | None = None,
    purchase_order_id: UUID | None = None,
    invoice_id: UUID | None = None,
    grn_id: UUID | None = None,
    detected_at: datetime | None = None,
) -> AnomalySignal:
    title, explanation = explain_from_evidence(anomaly_type.value, evidence)
    return AnomalySignal(
        anomaly_type=anomaly_type,
        severity=severity,
        score=_score(severity),
        vendor_id=vendor_id,
        purchase_order_id=purchase_order_id,
        invoice_id=invoice_id,
        grn_id=grn_id,
        detected_at=detected_at or _now(),
        title=title,
        explanation=explanation,
        evidence=evidence,
        fingerprint=fingerprint,
    )


class PriceVarianceRule:
    """Invoice line unit price vs linked PO line unit price."""

    def evaluate(
        self,
        *,
        invoice: InvoiceView,
        purchase_order: PurchaseOrderView | None,
        config: AnomalyConfig,
    ) -> list[AnomalySignal]:
        if purchase_order is None:
            return []
        po_lines = {line.id: line for line in purchase_order.lines}
        signals: list[AnomalySignal] = []
        for inv_line in invoice.lines:
            po_line = None
            if inv_line.purchase_order_line_id is not None:
                po_line = po_lines.get(inv_line.purchase_order_line_id)
            if po_line is None:
                continue
            po_price = Decimal(str(po_line.unit_price))
            inv_price = Decimal(str(inv_line.unit_price))
            variance_amount = abs(inv_price - po_price)
            variance_pct = percent_variance(po_price, inv_price)
            sev_name = severity_from_percent_thresholds(
                variance_pct,
                low=config.price_low_pct,
                medium=config.price_medium_pct,
                high=config.price_high_pct,
                critical=config.price_critical_pct,
            )
            if sev_name is None:
                continue
            severity = AnomalySeverity(sev_name)
            evidence = {
                "po_unit_price": decimal_str(po_price),
                "invoice_unit_price": decimal_str(inv_price),
                "variance_amount": decimal_str(variance_amount),
                "variance_percent": decimal_str(variance_pct.quantize(Decimal("0.01"))),
                "purchase_order_line_id": str(po_line.id),
                "invoice_line_id": str(inv_line.id),
                "line_number": inv_line.line_number,
            }
            fp = build_anomaly_fingerprint(
                AnomalyType.PRICE_VARIANCE.value,
                invoice.vendor_id,
                invoice.id,
                inv_line.id,
                po_line.id,
            )
            signals.append(
                _signal(
                    anomaly_type=AnomalyType.PRICE_VARIANCE,
                    severity=severity,
                    evidence=evidence,
                    fingerprint=fp,
                    vendor_id=invoice.vendor_id,
                    purchase_order_id=purchase_order.id,
                    invoice_id=invoice.id,
                )
            )
        return signals


class QuantityVarianceRule:
    """Invoice quantity vs PO ordered quantity on linked lines."""

    def evaluate(
        self,
        *,
        invoice: InvoiceView,
        purchase_order: PurchaseOrderView | None,
        config: AnomalyConfig,
    ) -> list[AnomalySignal]:
        if purchase_order is None:
            return []
        po_lines = {line.id: line for line in purchase_order.lines}
        signals: list[AnomalySignal] = []
        for inv_line in invoice.lines:
            po_line = None
            if inv_line.purchase_order_line_id is not None:
                po_line = po_lines.get(inv_line.purchase_order_line_id)
            if po_line is None:
                continue
            expected = Decimal(str(po_line.quantity))
            invoiced = Decimal(str(inv_line.quantity))
            if expected == 0 and invoiced == 0:
                continue
            variance_amount = abs(invoiced - expected)
            variance_pct = percent_variance(expected, invoiced)
            if expected == 0 and invoiced != 0:
                # Zero expected with nonzero invoice → treat as full variance.
                variance_pct = Decimal("100")
            sev_name = severity_from_percent_thresholds(
                variance_pct,
                low=config.quantity_low_pct,
                medium=config.quantity_medium_pct,
                high=config.quantity_high_pct,
                critical=config.quantity_critical_pct,
            )
            if sev_name is None:
                continue
            severity = AnomalySeverity(sev_name)
            evidence = {
                "expected_quantity": decimal_str(expected),
                "invoiced_quantity": decimal_str(invoiced),
                "variance_amount": decimal_str(variance_amount),
                "variance_percent": decimal_str(variance_pct.quantize(Decimal("0.01"))),
                "purchase_order_line_id": str(po_line.id),
                "invoice_line_id": str(inv_line.id),
                "line_number": inv_line.line_number,
            }
            fp = build_anomaly_fingerprint(
                AnomalyType.QUANTITY_VARIANCE.value,
                invoice.vendor_id,
                invoice.id,
                inv_line.id,
                po_line.id,
            )
            signals.append(
                _signal(
                    anomaly_type=AnomalyType.QUANTITY_VARIANCE,
                    severity=severity,
                    evidence=evidence,
                    fingerprint=fp,
                    vendor_id=invoice.vendor_id,
                    purchase_order_id=purchase_order.id,
                    invoice_id=invoice.id,
                )
            )
        return signals


class DuplicateInvoiceRule:
    """Same vendor + normalized invoice number across multiple invoice rows."""

    def evaluate(
        self,
        *,
        invoice: InvoiceView,
        sibling_invoices: list[InvoiceView],
    ) -> list[AnomalySignal]:
        normalized = normalize_invoice_number(invoice.invoice_number)
        matches = [
            inv
            for inv in sibling_invoices
            if normalize_invoice_number(inv.invoice_number) == normalized
        ]
        if len(matches) < 2:
            return []
        ids = sorted(str(inv.id) for inv in matches)
        evidence = {
            "vendor_id": str(invoice.vendor_id),
            "normalized_invoice_number": normalized,
            "invoice_ids": ids,
            "duplicate_count": len(matches),
        }
        fp = build_anomaly_fingerprint(
            AnomalyType.DUPLICATE_INVOICE.value,
            invoice.vendor_id,
            normalized,
        )
        return [
            _signal(
                anomaly_type=AnomalyType.DUPLICATE_INVOICE,
                severity=AnomalySeverity.HIGH,
                evidence=evidence,
                fingerprint=fp,
                vendor_id=invoice.vendor_id,
                invoice_id=invoice.id,
                purchase_order_id=invoice.purchase_order_id,
            )
        ]


class TimingAnomalyRule:
    """Unusual relative dates among PO / GRN / Invoice."""

    def evaluate(
        self,
        *,
        invoice: InvoiceView,
        purchase_order: PurchaseOrderView | None,
        goods_receipts: list[GoodsReceiptView],
        config: AnomalyConfig,
    ) -> list[AnomalySignal]:
        signals: list[AnomalySignal] = []
        inv_date = invoice.invoice_date

        if purchase_order is not None and inv_date < purchase_order.order_date:
            evidence = {
                "timing_kind": "invoice_before_po",
                "invoice_date": inv_date.isoformat(),
                "po_date": purchase_order.order_date.isoformat(),
                "purchase_order_id": str(purchase_order.id),
                "invoice_id": str(invoice.id),
            }
            fp = build_anomaly_fingerprint(
                AnomalyType.TIMING_ANOMALY.value,
                "invoice_before_po",
                invoice.id,
                purchase_order.id,
            )
            signals.append(
                _signal(
                    anomaly_type=AnomalyType.TIMING_ANOMALY,
                    severity=AnomalySeverity.HIGH,
                    evidence=evidence,
                    fingerprint=fp,
                    vendor_id=invoice.vendor_id,
                    purchase_order_id=purchase_order.id,
                    invoice_id=invoice.id,
                )
            )

        for grn in goods_receipts:
            if inv_date < grn.receipt_date:
                evidence = {
                    "timing_kind": "invoice_before_grn",
                    "invoice_date": inv_date.isoformat(),
                    "grn_date": grn.receipt_date.isoformat(),
                    "grn_id": str(grn.id),
                    "invoice_id": str(invoice.id),
                }
                fp = build_anomaly_fingerprint(
                    AnomalyType.TIMING_ANOMALY.value,
                    "invoice_before_grn",
                    invoice.id,
                    grn.id,
                )
                signals.append(
                    _signal(
                        anomaly_type=AnomalyType.TIMING_ANOMALY,
                        severity=AnomalySeverity.MEDIUM,
                        evidence=evidence,
                        fingerprint=fp,
                        vendor_id=invoice.vendor_id,
                        purchase_order_id=invoice.purchase_order_id,
                        invoice_id=invoice.id,
                        grn_id=grn.id,
                    )
                )

        if purchase_order is not None:
            delay = (inv_date - purchase_order.order_date).days
            if delay > config.timing_long_delay_days:
                evidence = {
                    "timing_kind": "long_po_to_invoice_delay",
                    "invoice_date": inv_date.isoformat(),
                    "po_date": purchase_order.order_date.isoformat(),
                    "delay_days": delay,
                    "threshold_days": config.timing_long_delay_days,
                    "purchase_order_id": str(purchase_order.id),
                    "invoice_id": str(invoice.id),
                }
                fp = build_anomaly_fingerprint(
                    AnomalyType.TIMING_ANOMALY.value,
                    "long_delay",
                    invoice.id,
                    purchase_order.id,
                )
                signals.append(
                    _signal(
                        anomaly_type=AnomalyType.TIMING_ANOMALY,
                        severity=AnomalySeverity.LOW,
                        evidence=evidence,
                        fingerprint=fp,
                        vendor_id=invoice.vendor_id,
                        purchase_order_id=purchase_order.id,
                        invoice_id=invoice.id,
                    )
                )
        return signals


class VendorSpikeRule:
    """Current invoice total vs simple average of prior vendor invoices."""

    def evaluate(
        self,
        *,
        invoice: InvoiceView,
        prior_invoices: list[InvoiceView],
        config: AnomalyConfig,
    ) -> list[AnomalySignal]:
        history = [inv for inv in prior_invoices if inv.id != invoice.id]
        if len(history) < config.vendor_spike_min_history:
            return []
        total = sum((Decimal(str(inv.total_amount)) for inv in history), Decimal("0"))
        baseline = (total / Decimal(len(history))).quantize(Decimal("0.0001"))
        if baseline <= 0:
            return []
        current = Decimal(str(invoice.total_amount))
        ratio = (current / baseline).quantize(Decimal("0.0001"))
        sev_name = severity_from_ratio_thresholds(
            ratio,
            medium=config.vendor_spike_medium_ratio,
            high=config.vendor_spike_high_ratio,
            critical=config.vendor_spike_critical_ratio,
        )
        if sev_name is None:
            return []
        severity = AnomalySeverity(sev_name)
        evidence = {
            "historical_invoice_count": len(history),
            "baseline_average": decimal_str(baseline),
            "current_value": decimal_str(current),
            "ratio": decimal_str(ratio),
        }
        fp = build_anomaly_fingerprint(
            AnomalyType.VENDOR_SPIKE.value,
            invoice.vendor_id,
            invoice.id,
        )
        return [
            _signal(
                anomaly_type=AnomalyType.VENDOR_SPIKE,
                severity=severity,
                evidence=evidence,
                fingerprint=fp,
                vendor_id=invoice.vendor_id,
                invoice_id=invoice.id,
                purchase_order_id=invoice.purchase_order_id,
            )
        ]


class RepeatedMismatchRule:
    """Elevated reconciliation-exception rate for a vendor in a time window."""

    def evaluate(
        self,
        *,
        vendor_id: UUID,
        invoice_count: int,
        exception_count: int,
        window_days: int,
        config: AnomalyConfig,
        as_of: date | None = None,
    ) -> list[AnomalySignal]:
        if invoice_count < config.repeated_mismatch_min_history:
            return []
        if invoice_count <= 0:
            return []
        rate = (Decimal(exception_count) / Decimal(invoice_count)).quantize(Decimal("0.0001"))
        sev_name = severity_from_rate_thresholds(
            rate,
            medium=config.repeated_mismatch_medium_rate,
            high=config.repeated_mismatch_high_rate,
            critical=config.repeated_mismatch_critical_rate,
        )
        if sev_name is None:
            return []
        severity = AnomalySeverity(sev_name)
        as_of_date = as_of or date.today()
        window_start = as_of_date - timedelta(days=window_days)
        evidence = {
            "invoice_count": invoice_count,
            "exception_count": exception_count,
            "exception_rate": decimal_str(rate),
            "window_days": window_days,
            "window_start": window_start.isoformat(),
            "window_end": as_of_date.isoformat(),
            "vendor_id": str(vendor_id),
        }
        # Fingerprint uses vendor + window end date (day granularity) so daily
        # re-runs upsert rather than proliferate; excludes volatile scores.
        fp = build_anomaly_fingerprint(
            AnomalyType.REPEATED_MISMATCH.value,
            vendor_id,
            window_days,
            as_of_date.isoformat(),
        )
        return [
            _signal(
                anomaly_type=AnomalyType.REPEATED_MISMATCH,
                severity=severity,
                evidence=evidence,
                fingerprint=fp,
                vendor_id=vendor_id,
            )
        ]
