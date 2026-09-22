"""Anomaly domain enums (M9.1). Explicit types only — no generic catch-all."""

from __future__ import annotations

from enum import StrEnum


class AnomalyType(StrEnum):
    """Registered anomaly signal types."""

    PRICE_VARIANCE = "PRICE_VARIANCE"
    QUANTITY_VARIANCE = "QUANTITY_VARIANCE"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    TIMING_ANOMALY = "TIMING_ANOMALY"
    VENDOR_SPIKE = "VENDOR_SPIKE"
    REPEATED_MISMATCH = "REPEATED_MISMATCH"


class AnomalySeverity(StrEnum):
    """Deterministic severity ladder (never LLM-chosen)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# Normalized severity score in [0, 1]. Not a probability.
SEVERITY_SCORE: dict[AnomalySeverity, str] = {
    AnomalySeverity.LOW: "0.25",
    AnomalySeverity.MEDIUM: "0.50",
    AnomalySeverity.HIGH: "0.75",
    AnomalySeverity.CRITICAL: "1.00",
}


class AnomalyScanType(StrEnum):
    """Explicit batch scan scopes (M9.2). No arbitrary types."""

    INVOICE = "INVOICE"
    VENDOR = "VENDOR"
    EXCEPTION = "EXCEPTION"
    FULL = "FULL"


class AnomalyScanStatus(StrEnum):
    """Scan job lifecycle."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AnomalyTrendPeriod(StrEnum):
    """Deterministic trend grouping."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
