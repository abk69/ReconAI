"""Risk scoring enums (M9.3). Explicit entity types and bands only."""

from __future__ import annotations

from enum import StrEnum

RISK_SCORE_VERSION = "m9.3-v1"


class RiskEntityType(StrEnum):
    """Supported risk profile entity types."""

    VENDOR = "VENDOR"
    INVOICE = "INVOICE"
    PURCHASE_ORDER = "PURCHASE_ORDER"


class RiskBand(StrEnum):
    """Internal risk-signal bands — not probabilities."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
