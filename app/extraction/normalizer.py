"""Deterministic normalization helpers for procurement values."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

_MONEY_CLEAN = re.compile(r"[,\s₹$€£]")
_PERCENT_CLEAN = re.compile(r"\s*%\s*$")
_MULTI_SPACE = re.compile(r"\s+")
_MISSING_VALUES = frozenset(
    {
        "not provided",
        "not available",
        "n/a",
        "na",
        "none",
        "null",
        "unknown",
        "not specified",
        "not applicable",
        "-",
        "--",
    }
)


def normalize_identifier(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = _MULTI_SPACE.sub(" ", value.strip())
    return cleaned or None


def is_missing_value(value: str | None) -> bool:
    """True when text states that a field was withheld, not when it names a record."""
    cleaned = normalize_identifier(value)
    if cleaned is None:
        return True
    return cleaned.casefold() in _MISSING_VALUES


def normalize_business_value(value: str | None) -> str | None:
    """Return a stored identifier, or None when the text says the field is absent."""
    if is_missing_value(value):
        return None
    return normalize_identifier(value)


def normalize_vendor_name(value: str | None) -> str | None:
    return normalize_business_value(value)


def normalize_money(value: str | Decimal | None) -> Decimal | None:
    """Parse money into Decimal. Rejects malformed input; never uses float."""
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    cleaned = _MONEY_CLEAN.sub("", raw)
    cleaned = cleaned.replace("(", "-").replace(")", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def normalize_quantity(value: str | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    raw = str(value).strip().replace(",", "")
    if not raw:
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def normalize_percentage(value: str | Decimal | None) -> Decimal | None:
    """Normalize 18%, 18.0 %, 0.18 into a fractional rate (0.18).

    Values already <= 1 are treated as fractions. Values > 1 are treated as
    percent points (18 → 0.18). Ambiguous empty input returns None.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        number = value
    else:
        raw = _PERCENT_CLEAN.sub("", str(value).strip())
        raw = raw.replace(",", "")
        if not raw:
            return None
        try:
            number = Decimal(raw)
        except InvalidOperation:
            return None

    if number < 0:
        return None
    if number > 1:
        return number / Decimal("100")
    return number


def normalize_date(value: str | date | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    raw = str(value).strip()
    if not raw:
        return None
    formats = (
        "%Y-%m-%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d-%m-%y",
        "%d/%m/%y",
        "%Y/%m/%d",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None
