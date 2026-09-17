"""Document extractor protocol and shared label patterns."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from uuid import UUID

from app.domain.enums import FieldConfidence
from app.extraction.schemas import ExtractedDocument, FieldEvidence

EXTRACTOR_VERSION = "m4-1.0"

LABEL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "invoice_number": [
        re.compile(
            r"(?:invoice\s*(?:number|no\.?|#)|inv\s*(?:no\.?|#))\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
    ],
    "po_number": [
        re.compile(
            r"(?:purchase\s*order\s*(?:number|no\.?|#)|p\.?o\.?\s*(?:number|no\.?|#)|po\s*(?:no\.?|#))\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
    ],
    "grn_number": [
        re.compile(
            r"\bgrn\s*(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
        re.compile(
            r"goods\s*receipt(?:\s*note)?\s+(?:number|no\.?|#)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
    ],
    "vendor_name": [
        re.compile(
            r"(?:vendor|supplier)\s*(?:name)?\s*[:\-]?\s*(.+)$",
            re.IGNORECASE | re.MULTILINE,
        ),
    ],
    "invoice_date": [
        re.compile(
            r"(?:invoice\s*date)\s*[:\-]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
            re.IGNORECASE,
        ),
    ],
    "order_date": [
        re.compile(
            r"(?:po\s*date|order\s*date|purchase\s*order\s*date)\s*[:\-]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
            re.IGNORECASE,
        ),
    ],
    "receipt_date": [
        re.compile(
            r"(?:receipt\s*date|received\s*date|grn\s*date)\s*[:\-]?\s*([0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})",
            re.IGNORECASE,
        ),
    ],
}


def find_labelled_value(text: str, field_name: str) -> tuple[str, str] | None:
    """Return (value, matched_snippet) for the first matching label pattern."""
    for pattern in LABEL_PATTERNS.get(field_name, []):
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            return value, match.group(0).strip()
    return None


def evidence_for_label(
    *,
    field_name: str,
    value: str,
    snippet: str,
    source_type: str,
    method: str,
    page: int | None = None,
    sheet: str | None = None,
    cell: str | None = None,
    confidence: FieldConfidence = FieldConfidence.HIGH,
) -> FieldEvidence:
    return FieldEvidence(
        field_name=field_name,
        value=value,
        raw_value=value,
        source_type=source_type,
        page=page,
        sheet=sheet,
        cell=cell,
        source_text=snippet,
        extraction_method=method,
        confidence=confidence,
        reason="Explicit labelled field matched",
    )


class DocumentExtractor(ABC):
    """Format-specific extractor producing a canonical raw ExtractedDocument."""

    name: str

    @abstractmethod
    def extract(
        self,
        *,
        document_id: UUID,
        data: bytes,
        filename: str,
        mime_type: str,
    ) -> ExtractedDocument:
        """Extract text/tables from file bytes."""


def select_extractor(extension: str, mime_type: str) -> DocumentExtractor:
    """Choose an extractor from extension/MIME. Raises ValueError if unsupported."""
    from app.extraction.image import ImageExtractor
    from app.extraction.pdf import PDFExtractor
    from app.extraction.xlsx import XLSXExtractor

    ext = extension.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    mime = (mime_type or "").split(";")[0].strip().lower()

    if ext == ".pdf" or mime == "application/pdf":
        return PDFExtractor()
    if ext == ".xlsx" or mime.endswith("spreadsheetml.sheet"):
        return XLSXExtractor()
    if ext in {".jpg", ".jpeg", ".png"} or mime in {"image/jpeg", "image/png"}:
        return ImageExtractor()
    raise ValueError(f"No extractor for extension '{ext}' / MIME '{mime}'.")


def extension_of(filename: str) -> str:
    return Path(filename).suffix.lower()
