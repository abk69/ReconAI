"""Cursor pagination helpers for anomaly signal listing (M9.2)."""

from __future__ import annotations

import base64
import binascii
from datetime import datetime
from uuid import UUID


class AnomalyCursorError(ValueError):
    """Invalid or malformed pagination cursor."""


def encode_anomaly_cursor(*, detected_at: datetime, anomaly_id: UUID) -> str:
    """Encode stable (detected_at DESC, id DESC) cursor."""
    ts = detected_at.isoformat()
    raw = f"{ts}|{anomaly_id}".encode()
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_anomaly_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Decode cursor into (detected_at, id). Raises AnomalyCursorError on failure."""
    if not cursor or not cursor.strip():
        raise AnomalyCursorError("Cursor must be a non-empty string.")
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise AnomalyCursorError("Cursor is not valid base64.") from exc
    parts = raw.split("|", 1)
    if len(parts) != 2:
        raise AnomalyCursorError("Cursor payload must be detected_at|id.")
    ts_raw, id_raw = parts
    try:
        detected_at = datetime.fromisoformat(ts_raw)
    except ValueError as exc:
        raise AnomalyCursorError("Cursor detected_at is not a valid ISO timestamp.") from exc
    try:
        anomaly_id = UUID(id_raw)
    except ValueError as exc:
        raise AnomalyCursorError("Cursor id is not a valid UUID.") from exc
    return detected_at, anomaly_id
