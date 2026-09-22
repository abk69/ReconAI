"""Pure deterministic risk score formula (M9.3).

Formula
-------
For each anomaly signal ``i`` with type ``T``, severity ``S``, age ``d`` days
relative to reference date ``as_of``:

    raw_i = weight(T) × severity_mult(S) × recency_mult(d)

Group by type ``T``:

    uncapped_T = Σ raw_i for signals of type T
    capped_T   = min(uncapped_T, cap(T))

Aggregate:

    aggregate = Σ capped_T over all types

Normalize to 0–100 using the sum of per-type caps as the theoretical maximum:

    MAX = Σ cap(T)   # default 180
    score = min(100, round_half_up(aggregate × 100 / MAX))

Risk band (defaults):

    0–24 LOW · 25–49 MEDIUM · 50–74 HIGH · 75–100 CRITICAL

This score is a deterministic aggregation of observed anomaly signals.
It is **not** a probability of fraud and is **not** a fraud determination.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol
from uuid import UUID

from app.anomaly.enums import AnomalySeverity, AnomalyType
from app.risk.contracts import (
    RiskScoringConfig,
    SignalContribution,
    TypeBreakdown,
)
from app.risk.enums import RiskBand


class SignalView(Protocol):
    id: UUID
    anomaly_type: str
    severity: str
    fingerprint: str
    detected_at: datetime


def days_since(*, detected_at: datetime, as_of: date) -> int:
    """Non-negative whole days between signal date and reference date."""
    det = detected_at.date() if isinstance(detected_at, datetime) else detected_at
    delta = (as_of - det).days
    return max(0, delta)


def recency_multiplier(days: int, config: RiskScoringConfig) -> Decimal:
    if days <= config.recency_full_days:
        return config.recency_full_mult
    if days <= config.recency_high_days:
        return config.recency_high_mult
    if days <= config.recency_mid_days:
        return config.recency_mid_mult
    return config.recency_old_mult


def band_for_score(score: int, config: RiskScoringConfig) -> RiskBand:
    if score >= config.band_critical_min:
        return RiskBand.CRITICAL
    if score >= config.band_high_min:
        return RiskBand.HIGH
    if score >= config.band_medium_min:
        return RiskBand.MEDIUM
    return RiskBand.LOW


def normalize_score(aggregate: Decimal, config: RiskScoringConfig) -> int:
    """Map aggregate capped contributions onto integer 0–100."""
    max_agg = config.max_aggregate()
    if max_agg <= 0:
        return 0
    scaled = (aggregate * Decimal("100")) / max_agg
    rounded = int(scaled.to_integral_value(rounding=ROUND_HALF_UP))
    return max(0, min(100, rounded))


def compute_contributions(
    signals: list[SignalView],
    *,
    as_of: date,
    config: RiskScoringConfig,
) -> list[SignalContribution]:
    contributions: list[SignalContribution] = []
    for sig in signals:
        atype = AnomalyType(sig.anomaly_type)
        sev = AnomalySeverity(sig.severity)
        weight = config.weight_for(atype)
        sev_m = config.severity_multiplier(sev)
        rec_m = recency_multiplier(days_since(detected_at=sig.detected_at, as_of=as_of), config)
        raw = (weight * sev_m * rec_m).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        contributions.append(
            SignalContribution(
                anomaly_type=atype,
                severity=sev,
                base_weight=weight,
                severity_multiplier=sev_m,
                recency_multiplier=rec_m,
                raw_contribution=raw,
                signal_id=sig.id,
                signal_fingerprint=sig.fingerprint,
                detected_at=sig.detected_at,
            )
        )
    return contributions


def compute_type_breakdown(
    contributions: list[SignalContribution],
    config: RiskScoringConfig,
) -> list[TypeBreakdown]:
    by_type: dict[AnomalyType, list[SignalContribution]] = defaultdict(list)
    for c in contributions:
        by_type[c.anomaly_type].append(c)

    breakdown: list[TypeBreakdown] = []
    for atype in sorted(by_type.keys(), key=lambda t: t.value):
        rows = by_type[atype]
        uncapped = sum((r.raw_contribution for r in rows), Decimal("0"))
        cap = config.cap_for(atype)
        capped = min(uncapped, cap)
        breakdown.append(
            TypeBreakdown(
                anomaly_type=atype,
                contribution=capped.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
                uncapped_contribution=uncapped.quantize(
                    Decimal("0.0001"), rounding=ROUND_HALF_UP
                ),
                signal_count=len(rows),
                cap=cap,
            )
        )
    return breakdown


def score_from_breakdown(breakdown: list[TypeBreakdown], config: RiskScoringConfig) -> int:
    aggregate = sum((b.contribution for b in breakdown), Decimal("0"))
    return normalize_score(aggregate, config)


def calculate_score(
    signals: list[SignalView],
    *,
    as_of: date,
    config: RiskScoringConfig | None = None,
) -> tuple[int, RiskBand, list[SignalContribution], list[TypeBreakdown], dict[str, int]]:
    """Full deterministic score pipeline (score, band, contributions, breakdown)."""
    cfg = config or RiskScoringConfig()
    contributions = compute_contributions(signals, as_of=as_of, config=cfg)
    breakdown = compute_type_breakdown(contributions, cfg)
    score = score_from_breakdown(breakdown, cfg)
    band = band_for_score(score, cfg)
    sev_dist: dict[str, int] = defaultdict(int)
    for c in contributions:
        sev_dist[c.severity.value] += 1
    return score, band, contributions, breakdown, dict(sev_dist)
