"""Normalized comparison helpers for evaluation metrics."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def normalize_string(value: Any) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).strip().split())
    return text.casefold() if text else None


def normalize_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError, TypeError):
        return None


def normalize_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def values_equal(expected: Any, actual: Any, *, kind: str = "auto") -> bool:
    """Compare values with explicit normalization by kind."""
    if kind == "decimal" or _looks_decimal(expected, actual, kind):
        left = normalize_decimal(expected)
        right = normalize_decimal(actual)
        if left is None and right is None:
            return expected is None and actual is None
        return left is not None and right is not None and left == right

    if kind == "date" or _looks_date(expected, actual, kind):
        left = normalize_date(expected)
        right = normalize_date(actual)
        return left is not None and right is not None and left == right

    left = normalize_string(expected)
    right = normalize_string(actual)
    return left == right


def _looks_decimal(expected: Any, actual: Any, kind: str) -> bool:
    if kind != "auto":
        return False
    return isinstance(expected, Decimal) or isinstance(actual, Decimal)


def _looks_date(expected: Any, actual: Any, kind: str) -> bool:
    if kind != "auto":
        return False
    return isinstance(expected, (date, datetime)) or isinstance(actual, (date, datetime))


def ratio(numerator: int, denominator: int) -> Decimal:
    if denominator <= 0:
        return Decimal("0")
    return (Decimal(numerator) / Decimal(denominator)).quantize(Decimal("0.0001"))
