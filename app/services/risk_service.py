"""Risk scoring service — consumes persisted anomaly signals (M9.3)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import (
    AnomalySignalRecord,
    Invoice,
    PurchaseOrder,
    RiskProfileRecord,
    Vendor,
)
from app.risk.contracts import RiskProfileResult, RiskScoringConfig
from app.risk.enums import RISK_SCORE_VERSION, RiskEntityType
from app.risk.profiles import build_profile


class RiskNotFoundError(Exception):
    """Entity missing."""


class RiskServiceError(Exception):
    """Risk domain validation error."""


def config_from_settings(settings: Settings | None = None) -> RiskScoringConfig:
    s = settings or get_settings()
    return RiskScoringConfig(
        score_version=s.risk_score_version or RISK_SCORE_VERSION,
        weight_price_variance=Decimal(s.risk_weight_price_variance),
        weight_quantity_variance=Decimal(s.risk_weight_quantity_variance),
        weight_duplicate_invoice=Decimal(s.risk_weight_duplicate_invoice),
        weight_timing_anomaly=Decimal(s.risk_weight_timing_anomaly),
        weight_vendor_spike=Decimal(s.risk_weight_vendor_spike),
        weight_repeated_mismatch=Decimal(s.risk_weight_repeated_mismatch),
        cap_price_variance=Decimal(s.risk_cap_price_variance),
        cap_quantity_variance=Decimal(s.risk_cap_quantity_variance),
        cap_duplicate_invoice=Decimal(s.risk_cap_duplicate_invoice),
        cap_timing_anomaly=Decimal(s.risk_cap_timing_anomaly),
        cap_vendor_spike=Decimal(s.risk_cap_vendor_spike),
        cap_repeated_mismatch=Decimal(s.risk_cap_repeated_mismatch),
        band_medium_min=s.risk_band_medium_min,
        band_high_min=s.risk_band_high_min,
        band_critical_min=s.risk_band_critical_min,
    )


class RiskService:
    """Calculate and persist immutable risk profiles from anomaly signals."""

    def __init__(
        self,
        session: Session,
        *,
        config: RiskScoringConfig | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._config = config or config_from_settings(settings)

    def calculate_vendor_risk(
        self,
        vendor_id: UUID,
        *,
        as_of: date | None = None,
        commit: bool = True,
    ) -> RiskProfileRecord:
        if self._session.get(Vendor, vendor_id) is None:
            raise RiskNotFoundError(f"Vendor {vendor_id} not found")
        ref = as_of or date.today()
        signals = list(
            self._session.scalars(
                select(AnomalySignalRecord).where(
                    AnomalySignalRecord.vendor_id == vendor_id,
                    AnomalySignalRecord.detected_at
                    <= datetime.combine(ref, datetime.max.time()).replace(tzinfo=UTC),
                )
            ).all()
        )
        return self._persist_profile(
            entity_type=RiskEntityType.VENDOR,
            entity_id=vendor_id,
            signals=signals,
            as_of=ref,
            commit=commit,
        )

    def calculate_invoice_risk(
        self,
        invoice_id: UUID,
        *,
        as_of: date | None = None,
        commit: bool = True,
    ) -> RiskProfileRecord:
        if self._session.get(Invoice, invoice_id) is None:
            raise RiskNotFoundError(f"Invoice {invoice_id} not found")
        ref = as_of or date.today()
        signals = list(
            self._session.scalars(
                select(AnomalySignalRecord).where(
                    AnomalySignalRecord.invoice_id == invoice_id,
                    AnomalySignalRecord.detected_at
                    <= datetime.combine(ref, datetime.max.time()).replace(tzinfo=UTC),
                )
            ).all()
        )
        return self._persist_profile(
            entity_type=RiskEntityType.INVOICE,
            entity_id=invoice_id,
            signals=signals,
            as_of=ref,
            commit=commit,
        )

    def calculate_po_risk(
        self,
        purchase_order_id: UUID,
        *,
        as_of: date | None = None,
        commit: bool = True,
    ) -> RiskProfileRecord:
        if self._session.get(PurchaseOrder, purchase_order_id) is None:
            raise RiskNotFoundError(f"PurchaseOrder {purchase_order_id} not found")
        ref = as_of or date.today()
        signals = list(
            self._session.scalars(
                select(AnomalySignalRecord).where(
                    AnomalySignalRecord.purchase_order_id == purchase_order_id,
                    AnomalySignalRecord.detected_at
                    <= datetime.combine(ref, datetime.max.time()).replace(tzinfo=UTC),
                )
            ).all()
        )
        return self._persist_profile(
            entity_type=RiskEntityType.PURCHASE_ORDER,
            entity_id=purchase_order_id,
            signals=signals,
            as_of=ref,
            commit=commit,
        )

    def get_latest_profile(
        self,
        *,
        entity_type: RiskEntityType | str,
        entity_id: UUID,
        score_version: str | None = None,
        as_of: date | None = None,
    ) -> RiskProfileRecord | None:
        etype = RiskEntityType(entity_type).value
        stmt = select(RiskProfileRecord).where(
            RiskProfileRecord.entity_type == etype,
            RiskProfileRecord.entity_id == entity_id,
        )
        if score_version is not None:
            stmt = stmt.where(RiskProfileRecord.score_version == score_version)
        if as_of is not None:
            stmt = stmt.where(RiskProfileRecord.as_of == as_of)
        stmt = stmt.order_by(
            RiskProfileRecord.as_of.desc(),
            RiskProfileRecord.calculated_at.desc(),
        )
        return self._session.scalars(stmt).first()

    def get_or_calculate(
        self,
        *,
        entity_type: RiskEntityType,
        entity_id: UUID,
        as_of: date | None = None,
        commit: bool = True,
    ) -> RiskProfileRecord:
        """Return profile for entity+version+as_of, calculating if absent."""
        ref = as_of or date.today()
        existing = self.get_latest_profile(
            entity_type=entity_type,
            entity_id=entity_id,
            score_version=self._config.score_version,
            as_of=ref,
        )
        if existing is not None:
            return existing
        if entity_type is RiskEntityType.VENDOR:
            return self.calculate_vendor_risk(entity_id, as_of=ref, commit=commit)
        if entity_type is RiskEntityType.INVOICE:
            return self.calculate_invoice_risk(entity_id, as_of=ref, commit=commit)
        if entity_type is RiskEntityType.PURCHASE_ORDER:
            return self.calculate_po_risk(entity_id, as_of=ref, commit=commit)
        raise RiskServiceError(f"Unsupported entity type {entity_type}")

    def _persist_profile(
        self,
        *,
        entity_type: RiskEntityType,
        entity_id: UUID,
        signals: list[AnomalySignalRecord],
        as_of: date,
        commit: bool,
    ) -> RiskProfileRecord:
        result = build_profile(
            entity_type=entity_type,
            entity_id=entity_id,
            signals=signals,
            as_of=as_of,
            config=self._config,
        )
        # Reuse identical fingerprint (same inputs).
        by_fp = self._session.scalar(
            select(RiskProfileRecord).where(
                RiskProfileRecord.fingerprint == result.fingerprint
            )
        )
        if by_fp is not None:
            return by_fp

        # Unique entity+version+as_of — return existing without overwrite.
        by_key = self._session.scalar(
            select(RiskProfileRecord).where(
                RiskProfileRecord.entity_type == entity_type.value,
                RiskProfileRecord.entity_id == entity_id,
                RiskProfileRecord.score_version == result.score_version,
                RiskProfileRecord.as_of == as_of,
            )
        )
        if by_key is not None:
            return by_key

        payload = _breakdown_payload(result)
        row = RiskProfileRecord(
            entity_type=result.entity_type.value,
            entity_id=result.entity_id,
            score=result.score,
            risk_band=result.risk_band.value,
            score_version=result.score_version,
            as_of=result.as_of,
            calculated_at=result.calculated_at,
            signal_count=result.signal_count,
            breakdown=payload,
            fingerprint=result.fingerprint,
        )
        self._session.add(row)
        self._session.flush()
        if commit:
            self._session.commit()
            self._session.refresh(row)
        return row


def _breakdown_payload(result: RiskProfileResult) -> dict:
    return {
        "score": result.score,
        "risk_band": result.risk_band.value,
        "severity_distribution": result.severity_distribution,
        "type_breakdown": [
            {
                "anomaly_type": b.anomaly_type.value,
                "contribution": str(b.contribution),
                "uncapped_contribution": str(b.uncapped_contribution),
                "signal_count": b.signal_count,
                "cap": str(b.cap),
            }
            for b in result.breakdown
        ],
        "contributing_signals": [
            {
                "anomaly_type": c.anomaly_type.value,
                "severity": c.severity.value,
                "base_weight": str(c.base_weight),
                "severity_multiplier": str(c.severity_multiplier),
                "recency_multiplier": str(c.recency_multiplier),
                "raw_contribution": str(c.raw_contribution),
                "capped_contribution": None,  # caps applied at type level
                "signal_id": str(c.signal_id),
                "signal_fingerprint": c.signal_fingerprint,
                "detected_at": c.detected_at.isoformat(),
            }
            for c in result.contributing_signals
        ],
        "formula_notes": result.formula_notes,
    }
