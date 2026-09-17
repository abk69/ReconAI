"""Helpers for applying field-path corrections to candidate dicts."""

from __future__ import annotations

import copy
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

_DECIMAL_FIELDS = frozenset(
    {
        "quantity",
        "unit_price",
        "tax_rate",
        "subtotal",
        "tax_amount",
        "total_amount",
        "received_quantity",
    }
)
_DATE_FIELDS = frozenset({"order_date", "receipt_date", "invoice_date"})
_PATH_SEGMENT = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_]*)(?:\[(\d+)\])?$")


class CandidatePathError(Exception):
    """Invalid field path or correction value."""


def deep_copy_candidate(candidate: dict[str, Any] | None) -> dict[str, Any] | None:
    if candidate is None:
        return None
    return copy.deepcopy(candidate)


def get_field_value(candidate: dict[str, Any], field_path: str) -> Any:
    """Read a value by dotted path, e.g. ``lines[0].quantity``."""
    node: Any = candidate
    for segment in field_path.split("."):
        match = _PATH_SEGMENT.match(segment)
        if match is None:
            raise CandidatePathError(f"Invalid field path segment: {segment!r}")
        key, index = match.group(1), match.group(2)
        if not isinstance(node, dict) or key not in node:
            raise CandidatePathError(f"Field path not found: {field_path}")
        node = node[key]
        if index is not None:
            idx = int(index)
            if not isinstance(node, list) or idx < 0 or idx >= len(node):
                raise CandidatePathError(f"Field path index out of range: {field_path}")
            node = node[idx]
    return node


def set_field_value(candidate: dict[str, Any], field_path: str, value: Any) -> None:
    """Set a value by dotted path, mutating ``candidate`` in place."""
    segments = field_path.split(".")
    node: Any = candidate
    for segment in segments[:-1]:
        match = _PATH_SEGMENT.match(segment)
        if match is None:
            raise CandidatePathError(f"Invalid field path segment: {segment!r}")
        key, index = match.group(1), match.group(2)
        if not isinstance(node, dict) or key not in node:
            raise CandidatePathError(f"Field path not found: {field_path}")
        node = node[key]
        if index is not None:
            idx = int(index)
            if not isinstance(node, list) or idx < 0 or idx >= len(node):
                raise CandidatePathError(f"Field path index out of range: {field_path}")
            node = node[idx]

    last = segments[-1]
    match = _PATH_SEGMENT.match(last)
    if match is None:
        raise CandidatePathError(f"Invalid field path segment: {last!r}")
    key, index = match.group(1), match.group(2)
    leaf_name = key

    if index is not None:
        if not isinstance(node, dict) or key not in node:
            raise CandidatePathError(f"Field path not found: {field_path}")
        seq = node[key]
        idx = int(index)
        if not isinstance(seq, list) or idx < 0 or idx >= len(seq):
            raise CandidatePathError(f"Field path index out of range: {field_path}")
        # Setting an entire list element object is allowed; scalar leaf uses key only.
        raise CandidatePathError(
            f"Cannot assign directly to indexed container segment {last!r}; "
            "use a leaf path such as lines[0].quantity."
        )

    if not isinstance(node, dict):
        raise CandidatePathError(f"Field path parent is not an object: {field_path}")

    coerced = coerce_correction_value(leaf_name, value)
    node[key] = coerced


def coerce_correction_value(field_name: str, value: Any) -> Any:
    """Validate and coerce a corrected value using domain rules."""
    if value is None:
        return None

    if field_name in _DECIMAL_FIELDS:
        try:
            dec = Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError) as exc:
            raise CandidatePathError(f"Field {field_name} must be a valid Decimal value.") from exc
        if field_name in {"quantity", "received_quantity"} and dec <= 0:
            raise CandidatePathError(f"Field {field_name} must be positive.")
        if field_name in {"unit_price", "subtotal", "tax_amount", "total_amount"} and dec < 0:
            raise CandidatePathError(f"Field {field_name} cannot be negative.")
        if field_name == "tax_rate" and dec < 0:
            raise CandidatePathError("tax_rate cannot be negative.")
        return str(dec)

    if field_name in _DATE_FIELDS:
        if isinstance(value, date) and not isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, datetime):
            return value.date().isoformat()
        text = str(value).strip()
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError as exc:
            raise CandidatePathError(
                f"Field {field_name} must be an ISO date (YYYY-MM-DD)."
            ) from exc

    if field_name in {
        "po_number",
        "grn_number",
        "invoice_number",
        "vendor_name",
        "currency",
        "description",
        "reference",
    }:
        text = str(value).strip()
        if not text:
            raise CandidatePathError(f"Field {field_name} cannot be empty.")
        if field_name == "currency" and len(text) != 3:
            raise CandidatePathError("currency must be a 3-letter code.")
        return text

    if field_name == "line_number":
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise CandidatePathError("line_number must be an integer.") from exc
        if number < 1:
            raise CandidatePathError("line_number must be >= 1.")
        return number

    return value


def serialize_value(value: Any) -> Any:
    """JSON-safe serialization for audit storage (Decimal → str)."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value
