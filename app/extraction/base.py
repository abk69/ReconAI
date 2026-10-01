"""Document extractor protocol and shared label patterns."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.domain.enums import FieldConfidence
from app.extraction.normalizer import is_missing_value, normalize_business_value
from app.extraction.schemas import ExtractedDocument, FieldEvidence

_ALTERNATIVE_SPLIT = re.compile(r"\s+(?:/|\||\bor\b)\s+", re.IGNORECASE)
_DATE_TOKEN = re.compile(
    r"[0-9]{4}[-/][0-9]{1,2}[-/][0-9]{1,2}|[0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4}"
)
_ID_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9]*-\d[A-Za-z0-9\-_/]*|[A-Za-z0-9][A-Za-z0-9\-_/]*")

EXTRACTOR_VERSION = "m4-1.0"

LABEL_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "invoice_number": [
        re.compile(
            r"(?:invoice\s*(?:number|no\.?(?!\w)|#)|inv\s*(?:no\.?(?!\w)|#))\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
    ],
    "po_number": [
        re.compile(
            r"(?:purchase\s*order\s*(?:number|no\.?(?!\w)|#)|p\.?o\.?\s*(?:number|no\.?(?!\w)|#)|po\s*(?:no\.?(?!\w)|#))\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
        # Stacked or title layout: "PURCHASE ORDER" then "PO-5001" on the same or next line.
        # The identifier must contain a hyphen and a digit so "PO Number" is not captured as "PO".
        re.compile(
            r"(?:purchase\s*order|p\.?o\.?)\s*[:\-]?\s*([A-Za-z]{1,8}-\d[A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
    ],
    "grn_number": [
        re.compile(
            r"\bgrn\s*(?:number|no\.?(?!\w)|#)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
        re.compile(
            r"goods\s*receipt(?:\s*note)?\s+(?:number|no\.?(?!\w)|#)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
        re.compile(
            r"goods\s*receipt(?:\s*note)?\s*[:\-]?\s*([A-Za-z]{1,8}-\d[A-Za-z0-9\-_/]*)",
            re.IGNORECASE,
        ),
        re.compile(
            r"receipt\s*(?:number|no\.?(?!\w)|#)\s*[:\-]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]*)",
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
    "currency": [
        re.compile(
            r"currency\s*[:\-]?\s*([A-Za-z]{3})\b",
            re.IGNORECASE,
        ),
    ],
    "subtotal": [
        re.compile(
            r"sub\s*total\s*[:\-]?\s*([$€£₹]?\s*[0-9][0-9,]*(?:\.[0-9]+)?)",
            re.IGNORECASE,
        ),
    ],
    "tax_amount": [
        re.compile(
            r"(?<![\w])tax(?:\s*amount)?\s*[:\-]?\s*([$€£₹]?\s*[0-9][0-9,]*(?:\.[0-9]+)?)",
            re.IGNORECASE,
        ),
    ],
    "total_amount": [
        re.compile(
            r"(?<!sub)(?<![\w])(?:order\s+)?total(?:\s*amount)?\s*[:\-]?\s*([$€£₹]?\s*[0-9][0-9,]*(?:\.[0-9]+)?)",
            re.IGNORECASE,
        ),
    ],
}


@dataclass(frozen=True)
class LabelledRead:
    """One labelled field, or several conflicting values from the same line."""

    value: str | None
    alternatives: list[str]
    snippet: str


def _line_at(text: str, index: int) -> str:
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    if end < 0:
        end = len(text)
    return text[start:end].strip()


def _value_region(text: str, match: re.Match[str]) -> str:
    """The value text on the captured line, excluding a label that shares that line."""
    line_start = text.rfind("\n", 0, match.start(1)) + 1
    end = text.find("\n", match.start(1))
    if end < 0:
        end = len(text)
    if text[line_start : match.start(1)].strip():
        return text[match.start(1) : end].strip()
    return text[line_start:end].strip()


def _value_token(part: str, field_name: str) -> str | None:
    if field_name.endswith("date"):
        match = _DATE_TOKEN.search(part)
        return match.group(0) if match else None
    match = _ID_TOKEN.search(part)
    return match.group(0) if match else None


def _conflicting_values(line: str, field_name: str) -> list[str]:
    """Conflicting candidates written on one line. Repeated labels elsewhere are ignored."""
    if _ALTERNATIVE_SPLIT.search(line) is None:
        return []
    values: list[str] = []
    for part in _ALTERNATIVE_SPLIT.split(line):
        token = _value_token(part, field_name)
        if token is None or is_missing_value(token):
            continue
        if token not in values:
            values.append(token)
    return values if len(values) >= 2 else []


def read_labelled_field(text: str, field_name: str) -> LabelledRead | None:
    """Read a label. Skip a missing phrase. Do not keep only the first conflicting value."""
    for pattern in LABEL_PATTERNS.get(field_name, []):
        for match in pattern.finditer(text):
            line = _line_at(text, match.start(1))
            region = _value_region(text, match)
            missing = (
                is_missing_value(line)
                or is_missing_value(region)
                or is_missing_value(match.group(1))
            )
            if missing:
                continue
            alternatives = _conflicting_values(region, field_name)
            if len(alternatives) >= 2:
                return LabelledRead(value=None, alternatives=alternatives, snippet=region)
            value = alternatives[0] if alternatives else normalize_business_value(match.group(1))
            if value is None:
                continue
            return LabelledRead(value=value, alternatives=[], snippet=match.group(0).strip())
    return None


def find_labelled_value(text: str, field_name: str) -> tuple[str, str] | None:
    """Return (value, matched_snippet) for one unambiguous labelled value."""
    found = read_labelled_field(text, field_name)
    if found is None or found.value is None:
        return None
    return found.value, found.snippet


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
