"""Build structured procurement candidates from raw extraction + normalization."""

from __future__ import annotations

import re

from app.domain.enums import DocumentType, FieldConfidence
from app.extraction.base import evidence_for_label, find_labelled_value
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
    *,
    source_type: str = "pdf_text",
    method: str = "label_regex",
) -> str | None:
    found = find_labelled_value(text, field_name)
    if not found:
        return None
    value, snippet = found
    evidence.append(
        evidence_for_label(
            field_name=field_name,
            value=value,
            snippet=snippet,
            source_type=source_type,
            method=method,
        )
    )
    return value


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
    inv_raw = _match_field(text, "invoice_number", evidence)
    po_raw = _match_field(text, "po_number", evidence)
    vendor_raw = _match_field(text, "vendor_name", evidence)
    date_raw = _match_field(text, "invoice_date", evidence)

    lines = _lines_from_tables(extracted, evidence) or _lines_from_text(text, evidence)
    candidate = InvoiceCandidate(
        invoice_number=normalize_identifier(inv_raw),
        po_number=normalize_identifier(po_raw),
        vendor_name=normalize_vendor_name(vendor_raw),
        invoice_date=normalize_date(date_raw),
        lines=lines,
        evidence=evidence,
    )
    return candidate, evidence


def _build_po(
    extracted: ExtractedDocument,
    text: str,
    evidence: list[FieldEvidence],
) -> tuple[PurchaseOrderCandidate, list[FieldEvidence]]:
    po_raw = _match_field(text, "po_number", evidence)
    vendor_raw = _match_field(text, "vendor_name", evidence)
    date_raw = _match_field(text, "order_date", evidence)
    lines = _lines_from_tables(extracted, evidence) or _lines_from_text(text, evidence)
    candidate = PurchaseOrderCandidate(
        po_number=normalize_identifier(po_raw),
        vendor_name=normalize_vendor_name(vendor_raw),
        order_date=normalize_date(date_raw),
        lines=lines,
        evidence=evidence,
    )
    return candidate, evidence


def _build_grn(
    extracted: ExtractedDocument,
    text: str,
    evidence: list[FieldEvidence],
) -> tuple[GoodsReceiptCandidate, list[FieldEvidence]]:
    grn_raw = _match_field(text, "grn_number", evidence)
    po_raw = _match_field(text, "po_number", evidence)
    vendor_raw = _match_field(text, "vendor_name", evidence)
    date_raw = _match_field(text, "receipt_date", evidence)
    lines = _lines_from_tables(extracted, evidence) or _lines_from_text(text, evidence)
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
