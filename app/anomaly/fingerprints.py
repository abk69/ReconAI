"""Deterministic SHA-256 fingerprints for anomaly signal identity."""

from __future__ import annotations

import hashlib
from typing import Any


def build_anomaly_fingerprint(*parts: Any) -> str:
    """Stable SHA-256 identity fingerprint.

    Include only stable anomaly identity parts (type, entity IDs, rule key).
    Do **not** include timestamps, random UUIDs, scores, or explanation text.
    """
    payload = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
