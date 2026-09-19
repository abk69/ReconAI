"""Normalized M4 vs Gemini candidate comparison."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.evaluation.metrics import normalize_date, normalize_decimal, normalize_string

FINANCIAL_FIELDS = frozenset(
    {
        "quantity",
        "unit_price",
        "tax_rate",
        "subtotal",
        "tax_amount",
        "total_amount",
    }
)
IDENTIFIER_FIELDS = frozenset(
    {
        "invoice_number",
        "po_number",
        "grn_number",
        "vendor_name",
        "currency",
    }
)
DATE_FIELDS = frozenset({"invoice_date", "order_date", "receipt_date"})


@dataclass
class FieldDiff:
    field_path: str
    status: str  # agreement | disagreement | m4_only | gemini_only | missing
    m4_value: Any = None
    gemini_value: Any = None


@dataclass
class ComparisonResult:
    agreements: list[str] = field(default_factory=list)
    disagreements: list[FieldDiff] = field(default_factory=list)
    m4_only: list[FieldDiff] = field(default_factory=list)
    gemini_only: list[FieldDiff] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    financially_significant_disagreements: list[FieldDiff] = field(default_factory=list)

    @property
    def has_financial_disagreement(self) -> bool:
        return bool(self.financially_significant_disagreements)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agreements": self.agreements,
            "disagreements": [d.__dict__ for d in self.disagreements],
            "m4_only": [d.__dict__ for d in self.m4_only],
            "gemini_only": [d.__dict__ for d in self.gemini_only],
            "missing": self.missing,
            "financially_significant_disagreements": [
                d.__dict__ for d in self.financially_significant_disagreements
            ],
            "has_financial_disagreement": self.has_financial_disagreement,
        }


def compare_candidates(
    m4: dict[str, Any] | None,
    gemini: dict[str, Any] | None,
) -> ComparisonResult:
    """Compare M4 and Gemini candidates using normalized equality."""
    m4 = m4 or {}
    gemini = gemini or {}
    result = ComparisonResult()

    header_keys = sorted(set(list(m4.keys()) + list(gemini.keys())) - {"lines", "evidence"})
    for key in header_keys:
        _compare_field(result, key, m4.get(key), gemini.get(key))

    m4_lines = list(m4.get("lines") or [])
    gemini_lines = list(gemini.get("lines") or [])
    count = max(len(m4_lines), len(gemini_lines))
    if len(m4_lines) != len(gemini_lines):
        result.disagreements.append(
            FieldDiff(
                field_path="lines.count",
                status="disagreement",
                m4_value=len(m4_lines),
                gemini_value=len(gemini_lines),
            )
        )
        result.financially_significant_disagreements.append(result.disagreements[-1])

    line_fields = ("line_number", "description", "quantity", "unit_price", "tax_rate", "reference")
    for idx in range(count):
        m4_line = m4_lines[idx] if idx < len(m4_lines) and isinstance(m4_lines[idx], dict) else {}
        g_line = (
            gemini_lines[idx]
            if idx < len(gemini_lines) and isinstance(gemini_lines[idx], dict)
            else {}
        )
        for lf in line_fields:
            path = f"lines[{idx}].{lf}"
            _compare_field(result, path, m4_line.get(lf), g_line.get(lf), leaf=lf)

    return result


def _compare_field(
    result: ComparisonResult,
    path: str,
    m4_value: Any,
    gemini_value: Any,
    *,
    leaf: str | None = None,
) -> None:
    leaf_name = leaf or path.split(".")[-1]
    m4_empty = _is_empty(m4_value)
    g_empty = _is_empty(gemini_value)

    if m4_empty and g_empty:
        result.missing.append(path)
        return
    if m4_empty and not g_empty:
        diff = FieldDiff(path, "gemini_only", None, gemini_value)
        result.gemini_only.append(diff)
        return
    if not m4_empty and g_empty:
        diff = FieldDiff(path, "m4_only", m4_value, None)
        result.m4_only.append(diff)
        return

    if values_agree(m4_value, gemini_value, field_name=leaf_name):
        result.agreements.append(path)
        return

    diff = FieldDiff(path, "disagreement", m4_value, gemini_value)
    result.disagreements.append(diff)
    if leaf_name in FINANCIAL_FIELDS | IDENTIFIER_FIELDS | DATE_FIELDS:
        result.financially_significant_disagreements.append(diff)


def values_agree(left: Any, right: Any, *, field_name: str) -> bool:
    if field_name in FINANCIAL_FIELDS:
        a = normalize_decimal(left)
        b = normalize_decimal(right)
        return a is not None and b is not None and a == b
    if field_name in DATE_FIELDS:
        a = normalize_date(left)
        b = normalize_date(right)
        return a is not None and b is not None and a == b
    if field_name == "line_number":
        try:
            return int(left) == int(right)
        except (TypeError, ValueError):
            return normalize_string(left) == normalize_string(right)
    return normalize_string(left) == normalize_string(right)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    return bool(isinstance(value, str) and not value.strip())


def parse_decimal_safe(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
