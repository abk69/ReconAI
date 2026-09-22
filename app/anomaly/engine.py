"""AnomalyEngine — orchestrates explicit M9.1 detection rules."""

from __future__ import annotations

from datetime import date
from uuid import UUID

from app.anomaly.contracts import AnomalyConfig, AnomalySignal
from app.anomaly.rules import (
    DuplicateInvoiceRule,
    GoodsReceiptView,
    InvoiceView,
    PriceVarianceRule,
    PurchaseOrderView,
    QuantityVarianceRule,
    RepeatedMismatchRule,
    TimingAnomalyRule,
    VendorSpikeRule,
)


class AnomalyEngine:
    """Deterministic orchestration of registered anomaly rules.

    Explicit entrypoints only — no unrestricted ``detect_everything``.
    """

    def __init__(self, config: AnomalyConfig | None = None) -> None:
        self._config = config or AnomalyConfig()
        self._price = PriceVarianceRule()
        self._quantity = QuantityVarianceRule()
        self._duplicate = DuplicateInvoiceRule()
        self._timing = TimingAnomalyRule()
        self._spike = VendorSpikeRule()
        self._repeated = RepeatedMismatchRule()

    @property
    def config(self) -> AnomalyConfig:
        return self._config

    def detect_for_invoice(
        self,
        *,
        invoice: InvoiceView,
        purchase_order: PurchaseOrderView | None,
        goods_receipts: list[GoodsReceiptView],
        sibling_invoices: list[InvoiceView],
        prior_vendor_invoices: list[InvoiceView],
    ) -> list[AnomalySignal]:
        """Run invoice-scoped rules and return structured signals."""
        signals: list[AnomalySignal] = []
        signals.extend(
            self._price.evaluate(
                invoice=invoice, purchase_order=purchase_order, config=self._config
            )
        )
        signals.extend(
            self._quantity.evaluate(
                invoice=invoice, purchase_order=purchase_order, config=self._config
            )
        )
        signals.extend(
            self._duplicate.evaluate(invoice=invoice, sibling_invoices=sibling_invoices)
        )
        signals.extend(
            self._timing.evaluate(
                invoice=invoice,
                purchase_order=purchase_order,
                goods_receipts=goods_receipts,
                config=self._config,
            )
        )
        signals.extend(
            self._spike.evaluate(
                invoice=invoice,
                prior_invoices=prior_vendor_invoices,
                config=self._config,
            )
        )
        return signals

    def detect_for_vendor(
        self,
        *,
        vendor_id: UUID,
        invoices: list[InvoiceView],
        invoice_count: int,
        exception_count: int,
        as_of: date | None = None,
    ) -> list[AnomalySignal]:
        """Run vendor-scoped rules (spike on latest invoice + repeated mismatch)."""
        signals: list[AnomalySignal] = []
        if invoices:
            latest = max(invoices, key=lambda inv: (inv.invoice_date, str(inv.id)))
            priors = [inv for inv in invoices if inv.id != latest.id]
            signals.extend(
                self._spike.evaluate(
                    invoice=latest, prior_invoices=priors, config=self._config
                )
            )
        signals.extend(
            self._repeated.evaluate(
                vendor_id=vendor_id,
                invoice_count=invoice_count,
                exception_count=exception_count,
                window_days=self._config.repeated_mismatch_window_days,
                config=self._config,
                as_of=as_of,
            )
        )
        return signals

    def detect_for_exception(
        self,
        *,
        invoice: InvoiceView | None,
        purchase_order: PurchaseOrderView | None,
        goods_receipts: list[GoodsReceiptView],
        sibling_invoices: list[InvoiceView],
        prior_vendor_invoices: list[InvoiceView],
        vendor_id: UUID | None,
        invoice_count: int,
        exception_count: int,
        as_of: date | None = None,
    ) -> list[AnomalySignal]:
        """Run rules relevant to a reconciliation exception's related documents."""
        signals: list[AnomalySignal] = []
        if invoice is not None:
            signals.extend(
                self.detect_for_invoice(
                    invoice=invoice,
                    purchase_order=purchase_order,
                    goods_receipts=goods_receipts,
                    sibling_invoices=sibling_invoices,
                    prior_vendor_invoices=prior_vendor_invoices,
                )
            )
        if vendor_id is not None:
            # Avoid double-counting spike if invoice path already ran spike.
            existing_fps = {s.fingerprint for s in signals}
            vendor_signals = self.detect_for_vendor(
                vendor_id=vendor_id,
                invoices=prior_vendor_invoices
                + ([invoice] if invoice is not None else []),
                invoice_count=invoice_count,
                exception_count=exception_count,
                as_of=as_of,
            )
            for sig in vendor_signals:
                if sig.fingerprint not in existing_fps:
                    signals.append(sig)
        return signals
