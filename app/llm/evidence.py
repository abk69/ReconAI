"""Evidence grounding — verify Gemini field values against document text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.llm.schemas import GeminiExtractionOutput, GeminiFieldEvidence

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w./%-]+", re.UNICODE)


@dataclass
class EvidenceCheckResult:
    is_grounded: bool
    unsupported_fields: list[str] = field(default_factory=list)
    details: list[dict[str, Any]] = field(default_factory=list)


def normalize_for_match(value: str) -> str:
    text = _WS.sub(" ", value.strip())
    return text.casefold()


def conservative_contains(haystack: str, needle: str) -> bool:
    """Conservative substring match after normalizing whitespace/case."""
    if not needle or not haystack:
        return False
    h = normalize_for_match(haystack)
    n = normalize_for_match(needle)
    if n in h:
        return True
    h2 = _PUNCT.sub("", h)
    n2 = _PUNCT.sub("", n)
    return bool(n2) and n2 in h2


def validate_evidence(
    output: GeminiExtractionOutput,
    *,
    document_text: str,
    tables_text: str = "",
) -> EvidenceCheckResult:
    """Reject Gemini values that have no supporting evidence in the document."""
    corpus = f"{document_text}\n{tables_text}"
    unsupported: list[str] = []
    details: list[dict[str, Any]] = []

    evidence_by_field: dict[str, list[GeminiFieldEvidence]] = {}
    for ev in output.evidence:
        evidence_by_field.setdefault(ev.field_name, []).append(ev)

    for field_name, value in _important_values(output):
        if value is None or str(value).strip() == "":
            continue
        value_str = str(value).strip()
        claimed = evidence_by_field.get(field_name) or []
        # Also accept evidence keyed without line path prefix for line fields.
        base_name = field_name.rsplit(".", 1)[-1]
        if base_name != field_name:
            claimed = claimed + (evidence_by_field.get(base_name) or [])

        snippet_ok = False
        value_in_doc = conservative_contains(corpus, value_str)

        for ev in claimed:
            snippet = ev.snippet or ""
            if snippet and conservative_contains(corpus, snippet):
                if conservative_contains(snippet, value_str) or value_in_doc:
                    snippet_ok = True
                    break
            elif value_in_doc:
                snippet_ok = True
                break

        if not claimed and value_in_doc:
            snippet_ok = True

        details.append(
            {
                "field_name": field_name,
                "value": value_str,
                "grounded": snippet_ok,
                "has_evidence_object": bool(claimed),
            }
        )
        if not snippet_ok:
            unsupported.append(field_name)

    return EvidenceCheckResult(
        is_grounded=len(unsupported) == 0,
        unsupported_fields=unsupported,
        details=details,
    )


def _important_values(output: GeminiExtractionOutput) -> list[tuple[str, str | None]]:
    pairs: list[tuple[str, str | None]] = [
        ("invoice_number", output.invoice_number),
        ("po_number", output.po_number),
        ("grn_number", output.grn_number),
        ("vendor_name", output.vendor_name),
        ("invoice_date", output.invoice_date),
        ("order_date", output.order_date),
        ("receipt_date", output.receipt_date),
    ]
    for idx, line in enumerate(output.lines):
        pairs.append((f"lines[{idx}].quantity", line.quantity))
        pairs.append((f"lines[{idx}].unit_price", line.unit_price))
        pairs.append((f"lines[{idx}].tax_rate", line.tax_rate))
    return pairs
