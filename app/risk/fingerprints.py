"""Deterministic risk profile fingerprints (M9.3)."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import date


def build_risk_fingerprint(
    *,
    entity_type: str,
    entity_id: object,
    score_version: str,
    as_of: date,
    signal_fingerprints: Sequence[str],
) -> str:
    """SHA-256 over stable identity + sorted contributing signal fingerprints.

    Excludes random UUIDs, scores, bands, and free-form explanations.
    """
    sorted_fps = sorted(signal_fingerprints)
    parts = [
        entity_type,
        str(entity_id),
        score_version,
        as_of.isoformat(),
        *sorted_fps,
    ]
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
