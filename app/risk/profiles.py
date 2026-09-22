"""Risk profile assembly helpers (M9.3)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import UUID

from app.risk.contracts import RiskProfileResult, RiskScoringConfig
from app.risk.enums import RISK_SCORE_VERSION, RiskEntityType
from app.risk.fingerprints import build_risk_fingerprint
from app.risk.scoring import SignalView, calculate_score


def build_profile(
    *,
    entity_type: RiskEntityType,
    entity_id: UUID,
    signals: list[SignalView],
    as_of: date,
    config: RiskScoringConfig | None = None,
    calculated_at: datetime | None = None,
) -> RiskProfileResult:
    """Assemble a RiskProfileResult from persisted anomaly signals."""
    cfg = config or RiskScoringConfig()
    score, band, contributions, breakdown, sev_dist = calculate_score(
        signals, as_of=as_of, config=cfg
    )
    fps = [c.signal_fingerprint for c in contributions]
    fingerprint = build_risk_fingerprint(
        entity_type=entity_type.value,
        entity_id=entity_id,
        score_version=cfg.score_version or RISK_SCORE_VERSION,
        as_of=as_of,
        signal_fingerprints=fps,
    )
    return RiskProfileResult(
        entity_type=entity_type,
        entity_id=entity_id,
        score=score,
        risk_band=band,
        score_version=cfg.score_version or RISK_SCORE_VERSION,
        calculated_at=calculated_at or datetime.now(UTC),
        as_of=as_of,
        signal_count=len(contributions),
        contributing_signals=contributions,
        breakdown=breakdown,
        severity_distribution=sev_dist,
        fingerprint=fingerprint,
    )
