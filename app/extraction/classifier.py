"""Deterministic document classification (no LLM)."""

from __future__ import annotations

import re

from app.domain.enums import DocumentType
from app.extraction.schemas import ExtractedDocument

_INVOICE_HINTS = re.compile(
    r"\b(invoice|tax\s*invoice|bill\s*to|amount\s*due)\b",
    re.IGNORECASE,
)
_PO_HINTS = re.compile(
    r"\b(purchase\s*order|ordered\s*by|ship\s*to)\b",
    re.IGNORECASE,
)
_GRN_HINTS = re.compile(
    r"\b(goods\s*receipt|goods\s*received|grn|received\s*quantity)\b",
    re.IGNORECASE,
)

_FILENAME_INVOICE = re.compile(r"inv(oice)?", re.IGNORECASE)
_FILENAME_PO = re.compile(r"(purchase[_\-]?order|\bpo\b)", re.IGNORECASE)
_FILENAME_GRN = re.compile(r"(grn|goods[_\-]?receipt)", re.IGNORECASE)


def classify_document(
    extracted: ExtractedDocument,
    *,
    declared_type: DocumentType | None = None,
    original_filename: str | None = None,
) -> DocumentType:
    """Classify using metadata, filename, and extracted keywords.

    Returns UNKNOWN when signals conflict or are weak — never guesses.
    """
    if declared_type is not None and declared_type is not DocumentType.UNKNOWN:
        return declared_type

    filename = original_filename or str(extracted.metadata.get("filename") or "")
    text = extracted.full_text
    labelled = extracted.metadata.get("labelled_fields") or {}

    votes: dict[DocumentType, int] = {
        DocumentType.INVOICE: 0,
        DocumentType.PO: 0,
        DocumentType.GRN: 0,
    }

    if _FILENAME_INVOICE.search(filename):
        votes[DocumentType.INVOICE] += 2
    if _FILENAME_PO.search(filename):
        votes[DocumentType.PO] += 2
    if _FILENAME_GRN.search(filename):
        votes[DocumentType.GRN] += 2

    if labelled.get("invoice_number"):
        votes[DocumentType.INVOICE] += 3
    if (
        labelled.get("po_number")
        and not labelled.get("invoice_number")
        and not labelled.get("grn_number")
    ):
        votes[DocumentType.PO] += 2
    if labelled.get("grn_number"):
        votes[DocumentType.GRN] += 3

    if _INVOICE_HINTS.search(text):
        votes[DocumentType.INVOICE] += 2
    if _PO_HINTS.search(text):
        votes[DocumentType.PO] += 2
    if _GRN_HINTS.search(text):
        votes[DocumentType.GRN] += 2

    ranked = sorted(votes.items(), key=lambda item: item[1], reverse=True)
    best_type, best_score = ranked[0]
    second_score = ranked[1][1]

    if best_score < 2:
        return DocumentType.UNKNOWN
    if best_score == second_score:
        return DocumentType.UNKNOWN
    return best_type
