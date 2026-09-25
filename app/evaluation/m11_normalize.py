"""Deterministic comparison. Formatting matches are not extraction errors.

Rules:
- Strings: trim and collapse whitespace. Vendor names and descriptions are
  casefolded. Identifiers keep case and punctuation.
- Dates: compare canonical dates. ISO dates parse. A day-first token parses
  only when the first number is greater than 12. Ambiguous month/day strings
  do not match.
- Decimals: parse after stripping currency symbols and thousands commas.
  Absolute tolerance is 0. 10 and 10.00 match. 18 and 0.18 do not.
- Currency: uppercase letters only. Symbols are not mapped to codes.
- Lines: pair on item identifier when both sides have one, otherwise on a
  unique normalized description. Order is not a match key.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

ABSOLUTE_NUMERIC_TOLERANCE = Decimal("0")

_MONEY_CHARS = re.compile(r"[,₹$€£\s]")
_SPACE = re.compile(r"\s+")
_ISO_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_DAY_FIRST = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")

HEADER_FIELDS = (
    "vendor_name",
    "po_number",
    "invoice_number",
    "grn_number",
    "invoice_date",
    "order_date",
    "receipt_date",
    "currency",
    "subtotal",
    "tax_amount",
    "total_amount",
)
LINE_FIELDS = (
    "item_identifier",
    "description",
    "quantity",
    "unit_price",
    "tax_rate",
    "line_total",
)
IDENTIFIER_FIELDS = frozenset({"po_number", "invoice_number", "grn_number", "item_identifier"})
NAME_FIELDS = frozenset({"vendor_name", "description"})
DATE_FIELDS = frozenset({"invoice_date", "order_date", "receipt_date"})
DECIMAL_FIELDS = frozenset(
    {
        "subtotal",
        "tax_amount",
        "total_amount",
        "quantity",
        "unit_price",
        "tax_rate",
        "line_total",
    }
)
CURRENCY_FIELDS = frozenset({"currency"})


def collapse(value: Any) -> str | None:
    if value is None:
        return None
    text = _SPACE.sub(" ", str(value).strip())
    return text or None


def normalize_identifier(value: Any) -> str | None:
    return collapse(value)


def normalize_name(value: Any) -> str | None:
    text = collapse(value)
    return text.casefold() if text else None


def normalize_currency(value: Any) -> str | None:
    text = collapse(value)
    if not text:
        return None
    letters = "".join(ch for ch in text if ch.isalpha())
    return letters.upper() or None


def normalize_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (bool, dict, list)):
        return None
    if isinstance(value, float):
        return None
    raw = _MONEY_CHARS.sub("", str(value).strip())
    if not raw:
        return None
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None


def decimals_equal(expected: Any, predicted: Any) -> bool:
    left = normalize_decimal(expected)
    right = normalize_decimal(predicted)
    if left is None or right is None:
        return False
    return abs(left - right) <= ABSOLUTE_NUMERIC_TOLERANCE


def normalize_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (dict, list, bool)):
        return None
    text = str(value).strip()
    iso = _ISO_DATE.match(text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
        return _safe_date(year, month, day)
    day_first = _DAY_FIRST.match(text)
    if day_first:
        day, month, year = (int(part) for part in day_first.groups())
        if day > 12:
            return _safe_date(year, month, day)
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def display(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    return collapse(value)
