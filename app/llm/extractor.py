"""Helpers to prepare M4 context for Gemini and map evidence into FieldEvidence."""

from __future__ import annotations

from typing import Any

from app.domain.enums import DocumentType, FieldConfidence
from app.extraction.schemas import FieldEvidence
from app.llm.schemas import GeminiExtractionOutput


def build_document_text_from_raw(raw_extraction: dict[str, Any] | None) -> str:
    """Prefer full_text / pages from M4 raw extraction — never storage paths."""
    if not raw_extraction:
        return ""
    full = raw_extraction.get("full_text")
    if isinstance(full, str) and full.strip():
        return full
    pages = raw_extraction.get("pages") or []
    if pages:
        return "\n".join(str(p) for p in pages)
    blocks = raw_extraction.get("text_blocks") or []
    parts = []
    for block in blocks:
        if isinstance(block, dict) and block.get("text"):
            parts.append(str(block["text"]))
        elif isinstance(block, str):
            parts.append(block)
    return "\n".join(parts)


def tables_from_raw(raw_extraction: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not raw_extraction:
        return []
    tables = raw_extraction.get("tables") or []
    return [t for t in tables if isinstance(t, dict)]


def gemini_evidence_to_field_evidence(
    output: GeminiExtractionOutput,
) -> list[FieldEvidence]:
    """Convert Gemini evidence objects into M4 FieldEvidence records."""
    items: list[FieldEvidence] = []
    for ev in output.evidence:
        items.append(
            FieldEvidence(
                field_name=ev.field_name,
                value=ev.value,
                raw_value=ev.snippet,
                source_type=ev.source_type or "document_text",
                page=ev.page,
                source_text=ev.snippet,
                extraction_method="gemini",
                confidence=FieldConfidence.MEDIUM,
                reason="Gemini-claimed evidence (application-verified separately)",
            )
        )
    return items


def coerce_document_type(value: str | None) -> DocumentType:
    if value in DocumentType._value2member_map_:
        return DocumentType(value)
    return DocumentType.UNKNOWN
