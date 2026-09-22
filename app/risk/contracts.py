"""Contracts and configuration for M9.3 risk scoring."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.anomaly.enums import AnomalySeverity, AnomalyType
from app.risk.enums import RISK_SCORE_VERSION, RiskBand, RiskEntityType


class RiskScoringConfig(BaseModel):
    """Configurable weights / caps / multipliers / bands (Decimal-safe)."""

    model_config = ConfigDict(extra="forbid")

    score_version: str = RISK_SCORE_VERSION

    # Base weights per anomaly type
    weight_price_variance: Decimal = Field(default=Decimal("15"))
    weight_quantity_variance: Decimal = Field(default=Decimal("15"))
    weight_duplicate_invoice: Decimal = Field(default=Decimal("25"))
    weight_timing_anomaly: Decimal = Field(default=Decimal("10"))
    weight_vendor_spike: Decimal = Field(default=Decimal("20"))
    weight_repeated_mismatch: Decimal = Field(default=Decimal("20"))

    # Per-type contribution caps (after summing uncapped contributions for that type)
    cap_price_variance: Decimal = Field(default=Decimal("30"))
    cap_quantity_variance: Decimal = Field(default=Decimal("30"))
    cap_duplicate_invoice: Decimal = Field(default=Decimal("40"))
    cap_timing_anomaly: Decimal = Field(default=Decimal("20"))
    cap_vendor_spike: Decimal = Field(default=Decimal("30"))
    cap_repeated_mismatch: Decimal = Field(default=Decimal("30"))

    # Severity multipliers
    severity_low: Decimal = Field(default=Decimal("0.25"))
    severity_medium: Decimal = Field(default=Decimal("0.50"))
    severity_high: Decimal = Field(default=Decimal("0.75"))
    severity_critical: Decimal = Field(default=Decimal("1.00"))

    # Recency windows (days inclusive upper bound for each bucket start)
    recency_full_days: int = Field(default=30, ge=0)  # 0..30 → 1.0
    recency_high_days: int = Field(default=90, ge=0)  # 31..90 → 0.75
    recency_mid_days: int = Field(default=180, ge=0)  # 91..180 → 0.50
    recency_full_mult: Decimal = Field(default=Decimal("1.00"))
    recency_high_mult: Decimal = Field(default=Decimal("0.75"))
    recency_mid_mult: Decimal = Field(default=Decimal("0.50"))
    recency_old_mult: Decimal = Field(default=Decimal("0.25"))  # >180

    # Band boundaries (inclusive): 0–24 LOW, 25–49 MEDIUM, 50–74 HIGH, 75–100 CRITICAL
    band_medium_min: int = Field(default=25, ge=0, le=100)
    band_high_min: int = Field(default=50, ge=0, le=100)
    band_critical_min: int = Field(default=75, ge=0, le=100)

    def weight_for(self, anomaly_type: AnomalyType | str) -> Decimal:
        key = AnomalyType(anomaly_type)
        return {
            AnomalyType.PRICE_VARIANCE: self.weight_price_variance,
            AnomalyType.QUANTITY_VARIANCE: self.weight_quantity_variance,
            AnomalyType.DUPLICATE_INVOICE: self.weight_duplicate_invoice,
            AnomalyType.TIMING_ANOMALY: self.weight_timing_anomaly,
            AnomalyType.VENDOR_SPIKE: self.weight_vendor_spike,
            AnomalyType.REPEATED_MISMATCH: self.weight_repeated_mismatch,
        }[key]

    def cap_for(self, anomaly_type: AnomalyType | str) -> Decimal:
        key = AnomalyType(anomaly_type)
        return {
            AnomalyType.PRICE_VARIANCE: self.cap_price_variance,
            AnomalyType.QUANTITY_VARIANCE: self.cap_quantity_variance,
            AnomalyType.DUPLICATE_INVOICE: self.cap_duplicate_invoice,
            AnomalyType.TIMING_ANOMALY: self.cap_timing_anomaly,
            AnomalyType.VENDOR_SPIKE: self.cap_vendor_spike,
            AnomalyType.REPEATED_MISMATCH: self.cap_repeated_mismatch,
        }[key]

    def severity_multiplier(self, severity: AnomalySeverity | str) -> Decimal:
        key = AnomalySeverity(severity)
        return {
            AnomalySeverity.LOW: self.severity_low,
            AnomalySeverity.MEDIUM: self.severity_medium,
            AnomalySeverity.HIGH: self.severity_high,
            AnomalySeverity.CRITICAL: self.severity_critical,
        }[key]

    def max_aggregate(self) -> Decimal:
        """Sum of per-type caps — denominator for 0–100 normalization."""
        return (
            self.cap_price_variance
            + self.cap_quantity_variance
            + self.cap_duplicate_invoice
            + self.cap_timing_anomaly
            + self.cap_vendor_spike
            + self.cap_repeated_mismatch
        )


class SignalContribution(BaseModel):
    """Per-signal explainable contribution line."""

    model_config = ConfigDict(extra="forbid")

    anomaly_type: AnomalyType
    severity: AnomalySeverity
    base_weight: Decimal
    severity_multiplier: Decimal
    recency_multiplier: Decimal
    raw_contribution: Decimal
    signal_id: UUID
    signal_fingerprint: str
    detected_at: datetime


class TypeBreakdown(BaseModel):
    """Per-anomaly-type capped contribution."""

    model_config = ConfigDict(extra="forbid")

    anomaly_type: AnomalyType
    contribution: Decimal
    uncapped_contribution: Decimal
    signal_count: int
    cap: Decimal


class RiskProfileResult(BaseModel):
    """Computed risk profile (not a fraud probability)."""

    model_config = ConfigDict(extra="forbid")

    entity_type: RiskEntityType
    entity_id: UUID
    score: int = Field(ge=0, le=100)
    risk_band: RiskBand
    score_version: str
    calculated_at: datetime
    as_of: date
    signal_count: int
    contributing_signals: list[SignalContribution]
    breakdown: list[TypeBreakdown]
    severity_distribution: dict[str, int]
    fingerprint: str
    formula_notes: str = (
        "Deterministic aggregation of anomaly signals; not a fraud probability."
    )
