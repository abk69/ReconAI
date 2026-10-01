"""Build structured procurement candidates from raw extraction + normalization."""

from __future__ import annotations

import re
from decimal import Decimal

from app.domain.enums import DocumentType, FieldConfidence
from app.extraction.base import evidence_for_label, read_labelled_field
from app.extraction.normalizer import (
    normalize_date,
    normalize_identifier,
    normalize_money,
    normalize_percentage,
    normalize_quantity,
    normalize_vendor_name,
)
from app.extraction.schemas import (
    CandidateLine,
    ExtractedDocument,
    FieldEvidence,
    GoodsReceiptCandidate,
    InvoiceCandidate,
    PurchaseOrderCandidate,
)

_LINE_HEADER = re.compile(
    r"^(?:line\s*(?:no\.?|#)?|item\s*(?:no\.?|#)?|#|description|qty|quantity|"
    r"unit\s*price|price|tax|gst)(?:\s*[|\t]|$)",
    re.IGNORECASE,
)
_STACKED_HEADER_FIELDS = {
    "sku": "reference",
    "sku item": "reference",
    "description": "description",
    "particulars": "description",
    "qty": "quantity",
    "quantity": "quantity",
    "received": "quantity",
    "unit": "unit",
    "uom": "unit",
    "price": "unit_price",
    "unit price": "unit_price",
    "rate": "unit_price",
    "amount": "amount",
    "line total": "amount",
    "tax": "tax_rate",
    "tax rate": "tax_rate",
    "gst": "tax_rate",
}
_STACKED_FOOTER = re.compile(
    r"^(?:sub\s*total|order\s*total|total|tax|received\s*lines|qa\s*note|synthetic)\b",
    re.IGNORECASE,
)


def build_candidate(
    extracted: ExtractedDocument,
    document_type: DocumentType,
) -> tuple[
    PurchaseOrderCandidate | GoodsReceiptCandidate | InvoiceCandidate | None,
    list[FieldEvidence],
]:
    """Produce a typed candidate with evidence. Returns None for UNKNOWN."""
    evidence: list[FieldEvidence] = []
    text = extracted.full_text

    if document_type is DocumentType.INVOICE:
        return _build_invoice(extracted, text, evidence)
    if document_type is DocumentType.PO:
        return _build_po(extracted, text, evidence)
    if document_type is DocumentType.GRN:
        return _build_grn(extracted, text, evidence)
    return None, evidence


def _match_field(
    text: str,
    field_name: str,
    evidence: list[FieldEvidence],
    ambiguities: list[dict[str, object]] | None = None,
    *,
    source_type: str = "pdf_text",
    method: str = "label_regex",
) -> str | None:
    found = read_labelled_field(text, field_name)
    if found is None:
        return None
    if found.alternatives:
        if ambiguities is not None:
            ambiguities.append({"field_name": field_name, "values": list(found.alternatives)})
        evidence.append(
            FieldEvidence(
                field_name=field_name,
                value=None,
                raw_value=" / ".join(found.alternatives),
                source_type=source_type,
                source_text=found.snippet,
                extraction_method="ambiguous_values",
                confidence=FieldConfidence.LOW,
                reason="Conflicting values on one labelled line require review",
            )
        )
        return None
    evidence.append(
        evidence_for_label(
            field_name=field_name,
            value=found.value or "",
            snippet=found.snippet,
            source_type=source_type,
            method=method,
        )
    )
    return found.value


def _lines_from_tables(
    extracted: ExtractedDocument, evidence: list[FieldEvidence]
) -> list[CandidateLine]:
    lines: list[CandidateLine] = []
    for table in extracted.tables:
        headers = [h.strip().lower() for h in table.headers]
        if not headers:
            continue
        qty_idx = _find_col(headers, ("qty", "quantity", "received"))
        price_idx = _find_col(headers, ("unit price", "price", "rate"))
        tax_idx = _find_col(headers, ("tax", "gst", "tax rate"))
        desc_idx = _find_col(headers, ("description", "item", "particulars"))
        if qty_idx is None and price_idx is None:
            continue
        for row_number, row in enumerate(table.rows, start=1):
            line_evidence: list[FieldEvidence] = []
            qty_raw = row[qty_idx] if qty_idx is not None and qty_idx < len(row) else None
            price_raw = row[price_idx] if price_idx is not None and price_idx < len(row) else None
            tax_raw = row[tax_idx] if tax_idx is not None and tax_idx < len(row) else None
            desc = row[desc_idx] if desc_idx is not None and desc_idx < len(row) else None
            qty = normalize_quantity(qty_raw)
            price = normalize_money(price_raw)
            tax = normalize_percentage(tax_raw)
            if qty is None and price is None:
                continue
            if qty_raw:
                line_evidence.append(
                    FieldEvidence(
                        field_name="quantity",
                        value=str(qty) if qty is not None else qty_raw,
                        raw_value=qty_raw,
                        source_type="xlsx_cell",
                        sheet=table.sheet,
                        extraction_method="table_column",
                        confidence=FieldConfidence.HIGH if qty is not None else FieldConfidence.LOW,
                        reason="Table column quantity",
                    )
                )
            if price_raw:
                line_evidence.append(
                    FieldEvidence(
                        field_name="unit_price",
                        value=str(price) if price is not None else price_raw,
                        raw_value=price_raw,
                        source_type="xlsx_cell",
                        sheet=table.sheet,
                        extraction_method="table_column",
                        confidence=FieldConfidence.HIGH
                        if price is not None
                        else FieldConfidence.LOW,
                        reason="Table column unit price",
                    )
                )
            lines.append(
                CandidateLine(
                    line_number=row_number,
                    description=normalize_identifier(desc),
                    quantity=qty,
                    unit_price=price,
                    tax_rate=tax,
                    evidence=line_evidence,
                )
            )
            evidence.extend(line_evidence)
    return lines


def _stacked_header_field(line: str) -> str | None:
    cleaned = re.sub(r"[^a-z0-9/ ]+", "", line.strip().lower())
    cleaned = re.sub(r"\s+", " ", cleaned.replace("/", " ")).strip()
    return _STACKED_HEADER_FIELDS.get(cleaned)


def _stacked_header_block(lines: list[str]) -> tuple[int, list[str]] | None:
    """Return the data start index and column fields for a vertical header block."""
    index = 0
    while index < len(lines):
        fields: list[str] = []
        cursor = index
        while cursor < len(lines):
            field = _stacked_header_field(lines[cursor])
            if field is None:
                break
            fields.append(field)
            cursor += 1
        if len(fields) >= 3 and "quantity" in fields:
            return cursor, fields
        index += 1
    return None


def _lines_from_stacked_columns(text: str, evidence: list[FieldEvidence]) -> list[CandidateLine]:
    """Read one cell per line after a vertical column-header block.

    Some PDFs emit each table cell on its own line. This parser runs only when
    that header block is present, so same-line ``description qty price`` text
    keeps the existing line pattern.
    """
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    found = _stacked_header_block(raw_lines)
    if found is None:
        return []
    start, fields = found
    width = len(fields)
    data = raw_lines[start:]
    lines: list[CandidateLine] = []
    cursor = 0
    while cursor + width <= len(data):
        chunk = data[cursor : cursor + width]
        if _STACKED_FOOTER.match(chunk[0]):
            break
        values = dict(zip(fields, chunk, strict=True))
        qty = normalize_quantity(values.get("quantity"))
        price = normalize_money(values.get("unit_price"))
        if qty is None and price is None:
            break
        tax = (
            normalize_percentage(values.get("tax_rate"))
            if values.get("tax_rate") is not None
            else None
        )
        line_ev = [
            FieldEvidence(
                field_name="quantity",
                value=str(qty) if qty is not None else values.get("quantity"),
                raw_value=values.get("quantity"),
                source_type="pdf_text",
                source_text=" | ".join(chunk),
                extraction_method="stacked_columns",
                confidence=FieldConfidence.MEDIUM if qty is not None else FieldConfidence.LOW,
                reason="Quantity from a vertical table layout",
            )
        ]
        if values.get("unit_price") is not None:
            line_ev.append(
                FieldEvidence(
                    field_name="unit_price",
                    value=str(price) if price is not None else values.get("unit_price"),
                    raw_value=values.get("unit_price"),
                    source_type="pdf_text",
                    source_text=" | ".join(chunk),
                    extraction_method="stacked_columns",
                    confidence=FieldConfidence.MEDIUM if price is not None else FieldConfidence.LOW,
                    reason="Unit price from a vertical table layout",
                )
            )
        evidence.extend(line_ev)
        lines.append(
            CandidateLine(
                line_number=len(lines) + 1,
                description=normalize_identifier(values.get("description")),
                quantity=qty,
                unit_price=price,
                tax_rate=tax,
                reference=normalize_identifier(values.get("reference")),
                evidence=line_ev,
            )
        )
        cursor += width
    return lines


def _lines_from_text(text: str, evidence: list[FieldEvidence]) -> list[CandidateLine]:
    """Conservative line parsing: qty/price pairs on the same line."""
    lines: list[CandidateLine] = []
    pattern = re.compile(
        r"(?P<desc>.+?)\s+(?P<qty>\d+(?:\.\d+)?)\s+(?P<price>\d+(?:,\d{3})*(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for idx, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or _LINE_HEADER.search(stripped):
            continue
        match = pattern.search(stripped)
        if not match:
            continue
        qty = normalize_quantity(match.group("qty"))
        price = normalize_money(match.group("price"))
        if qty is None or price is None:
            continue
        line_ev = [
            FieldEvidence(
                field_name="quantity",
                value=str(qty),
                raw_value=match.group("qty"),
                source_type="pdf_text",
                source_text=stripped,
                extraction_method="line_regex",
                confidence=FieldConfidence.MEDIUM,
                reason="Quantity/price pattern on text line",
            ),
            FieldEvidence(
                field_name="unit_price",
                value=str(price),
                raw_value=match.group("price"),
                source_type="pdf_text",
                source_text=stripped,
                extraction_method="line_regex",
                confidence=FieldConfidence.MEDIUM,
                reason="Quantity/price pattern on text line",
            ),
        ]
        evidence.extend(line_ev)
        lines.append(
            CandidateLine(
                line_number=idx,
                description=normalize_identifier(match.group("desc")),
                quantity=qty,
                unit_price=price,
                evidence=line_ev,
            )
        )
    return lines


def _currency_code(text: str, evidence: list[FieldEvidence]) -> str | None:
    raw = _match_field(text, "currency", evidence)
    if raw and re.fullmatch(r"[A-Za-z]{3}", raw.strip()):
        return raw.strip().upper()
    return None


def _labelled_money(text: str, field_name: str, evidence: list[FieldEvidence]) -> Decimal | None:
    return normalize_money(_match_field(text, field_name, evidence))


def _find_col(headers: list[str], names: tuple[str, ...]) -> int | None:
    for idx, header in enumerate(headers):
        for name in names:
            if name in header:
                return idx
    return None


def _build_invoice(
    extracted: ExtractedDocument,
    text: str,
    evidence: list[FieldEvidence],
) -> tuple[InvoiceCandidate, list[FieldEvidence]]:
    ambiguities: list[dict[str, object]] = []
    inv_raw = _match_field(text, "invoice_number", evidence, ambiguities)
    po_raw = _match_field(text, "po_number", evidence, ambiguities)
    vendor_raw = _match_field(text, "vendor_name", evidence, ambiguities)
    date_raw = _match_field(text, "invoice_date", evidence, ambiguities)
    extracted.metadata["ambiguous_fields"] = ambiguities

    lines = (
        _lines_from_tables(extracted, evidence)
        or _lines_from_stacked_columns(text, evidence)
        or _lines_from_text(text, evidence)
    )
    candidate = InvoiceCandidate(
        invoice_number=normalize_identifier(inv_raw),
        po_number=normalize_identifier(po_raw),
        vendor_name=normalize_vendor_name(vendor_raw),
        invoice_date=normalize_date(date_raw),
        currency=_currency_code(text, evidence),
        subtotal=_labelled_money(text, "subtotal", evidence),
        tax_amount=_labelled_money(text, "tax_amount", evidence),
        total_amount=_labelled_money(text, "total_amount", evidence),
        lines=lines,
        evidence=evidence,
    )
    return candidate, evidence


def _build_po(
    extracted: ExtractedDocument,
    text: str,
    evidence: list[FieldEvidence],
) -> tuple[PurchaseOrderCandidate, list[FieldEvidence]]:
    ambiguities: list[dict[str, object]] = []
    po_raw = _match_field(text, "po_number", evidence, ambiguities)
    vendor_raw = _match_field(text, "vendor_name", evidence, ambiguities)
    date_raw = _match_field(text, "order_date", evidence, ambiguities)
    extracted.metadata["ambiguous_fields"] = ambiguities
    lines = (
        _lines_from_tables(extracted, evidence)
        or _lines_from_stacked_columns(text, evidence)
        or _lines_from_text(text, evidence)
    )
    candidate = PurchaseOrderCandidate(
        po_number=normalize_identifier(po_raw),
        vendor_name=normalize_vendor_name(vendor_raw),
        order_date=normalize_date(date_raw),
        currency=_currency_code(text, evidence),
        lines=lines,
        evidence=evidence,
    )
    return candidate, evidence


def _build_grn(
    extracted: ExtractedDocument,
    text: str,
    evidence: list[FieldEvidence],
) -> tuple[GoodsReceiptCandidate, list[FieldEvidence]]:
    ambiguities: list[dict[str, object]] = []
    grn_raw = _match_field(text, "grn_number", evidence, ambiguities)
    po_raw = _match_field(text, "po_number", evidence, ambiguities)
    vendor_raw = _match_field(text, "vendor_name", evidence, ambiguities)
    date_raw = _match_field(text, "receipt_date", evidence, ambiguities)
    extracted.metadata["ambiguous_fields"] = ambiguities
    lines = (
        _lines_from_tables(extracted, evidence)
        or _lines_from_stacked_columns(text, evidence)
        or _lines_from_text(text, evidence)
    )
    # For GRN text lines, quantity may appear without price — reuse table qty only.
    if not lines:
        qty_match = re.search(
            r"(?:qty|quantity|received)\s*[:\-]?\s*(\d+(?:\.\d+)?)",
            text,
            re.IGNORECASE,
        )
        if qty_match:
            qty = normalize_quantity(qty_match.group(1))
            ev = FieldEvidence(
                field_name="quantity",
                value=str(qty) if qty is not None else qty_match.group(1),
                raw_value=qty_match.group(1),
                source_type="pdf_text",
                source_text=qty_match.group(0),
                extraction_method="label_regex",
                confidence=FieldConfidence.MEDIUM,
                reason="Received quantity label",
            )
            evidence.append(ev)
            lines = [CandidateLine(line_number=1, quantity=qty, evidence=[ev])]

    candidate = GoodsReceiptCandidate(
        grn_number=normalize_identifier(grn_raw),
        po_number=normalize_identifier(po_raw),
        vendor_name=normalize_vendor_name(vendor_raw),
        receipt_date=normalize_date(date_raw),
        lines=lines,
        evidence=evidence,
    )
    return candidate, evidence
