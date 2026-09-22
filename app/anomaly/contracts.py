"""Pydantic contracts for M9.1 anomaly signals and rule configuration."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.anomaly.enums import AnomalySeverity, AnomalyType


class AnomalyConfig(BaseModel):
    """Configuration-driven thresholds (Decimal-safe). Loaded from Settings."""

    model_config = ConfigDict(extra="forbid")

    price_low_pct: Decimal = Field(default=Decimal("5"), ge=Decimal("0"))
    price_medium_pct: Decimal = Field(default=Decimal("10"), ge=Decimal("0"))
    price_high_pct: Decimal = Field(default=Decimal("25"), ge=Decimal("0"))
    price_critical_pct: Decimal = Field(default=Decimal("50"), ge=Decimal("0"))

    quantity_low_pct: Decimal = Field(default=Decimal("5"), ge=Decimal("0"))
    quantity_medium_pct: Decimal = Field(default=Decimal("10"), ge=Decimal("0"))
    quantity_high_pct: Decimal = Field(default=Decimal("25"), ge=Decimal("0"))
    quantity_critical_pct: Decimal = Field(default=Decimal("50"), ge=Decimal("0"))

    vendor_spike_min_history: int = Field(default=3, ge=1)
    vendor_spike_medium_ratio: Decimal = Field(default=Decimal("2"), ge=Decimal("1"))
    vendor_spike_high_ratio: Decimal = Field(default=Decimal("3"), ge=Decimal("1"))
    vendor_spike_critical_ratio: Decimal = Field(default=Decimal("5"), ge=Decimal("1"))

    repeated_mismatch_min_history: int = Field(default=5, ge=1)
    repeated_mismatch_medium_rate: Decimal = Field(default=Decimal("0.30"), ge=Decimal("0"))
    repeated_mismatch_high_rate: Decimal = Field(default=Decimal("0.50"), ge=Decimal("0"))
    repeated_mismatch_critical_rate: Decimal = Field(default=Decimal("0.75"), ge=Decimal("0"))
    repeated_mismatch_window_days: int = Field(default=90, ge=1)

    timing_long_delay_days: int = Field(default=30, ge=1)


class AnomalySignal(BaseModel):
    """Structured anomaly signal — explainable risk, not a fraud determination."""

    model_config = ConfigDict(extra="forbid")

    anomaly_type: AnomalyType
    severity: AnomalySeverity
    score: Decimal = Field(
        description=(
            "Normalized severity score in [0, 1] derived from AnomalySeverity. "
            "Not a probability of fraud."
        ),
    )
    vendor_id: UUID | None = None
    purchase_order_id: UUID | None = None
    invoice_id: UUID | None = None
    grn_id: UUID | None = None
    detected_at: datetime
    title: str = Field(min_length=1, max_length=255)
    explanation: str = Field(min_length=1)
    evidence: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str = Field(min_length=64, max_length=128)
