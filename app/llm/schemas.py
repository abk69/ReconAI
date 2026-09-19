"""Pydantic schemas for Gemini structured extraction output.

Financial amounts are strings (Decimal-safe). Schema shape is enforced by
Gemini structured output; financial correctness is NOT.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

PROMPT_VERSION = "m6-1.0"

DocumentTypeLiteral = Literal["PO", "GRN", "INVOICE", "UNKNOWN"]


class GeminiFieldEvidence(BaseModel):
    """Evidence snippet claimed by the model for a field value."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    value: str | None = None
    source_type: str = "document_text"
    page: int | None = None
    snippet: str | None = None


class GeminiLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int | None = None
    description: str | None = None
    # Decimal-safe string representations (never float).
    quantity: str | None = None
    unit_price: str | None = None
    tax_rate: str | None = None
    reference: str | None = None


class GeminiExtractionOutput(BaseModel):
    """Structured candidate returned by Gemini (JSON Schema / response_schema)."""

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentTypeLiteral = "UNKNOWN"
    invoice_number: str | None = None
    po_number: str | None = None
    grn_number: str | None = None
    vendor_name: str | None = None
    order_date: str | None = None
    receipt_date: str | None = None
    invoice_date: str | None = None
    currency: str | None = None
    subtotal: str | None = None
    tax_amount: str | None = None
    total_amount: str | None = None
    lines: list[GeminiLineItem] = Field(default_factory=list)
    evidence: list[GeminiFieldEvidence] = Field(default_factory=list)
    notes: str | None = None


def gemini_output_to_candidate(output: GeminiExtractionOutput) -> dict[str, Any]:
    """Map Gemini structured output into an M4-compatible candidate dict."""
    doc_type = output.document_type
    lines: list[dict[str, Any]] = []
    for line in output.lines:
        item: dict[str, Any] = {
            "line_number": line.line_number,
            "description": line.description,
            "quantity": line.quantity,
            "unit_price": line.unit_price,
            "tax_rate": line.tax_rate,
            "reference": line.reference,
        }
        lines.append(item)

    if doc_type == "PO":
        return {
            "po_number": output.po_number,
            "vendor_name": output.vendor_name,
            "order_date": output.order_date,
            "currency": output.currency,
            "lines": lines,
        }
    if doc_type == "GRN":
        return {
            "grn_number": output.grn_number,
            "po_number": output.po_number,
            "receipt_date": output.receipt_date,
            "vendor_name": output.vendor_name,
            "lines": lines,
        }
    if doc_type == "INVOICE":
        return {
            "invoice_number": output.invoice_number,
            "po_number": output.po_number,
            "vendor_name": output.vendor_name,
            "invoice_date": output.invoice_date,
            "currency": output.currency,
            "subtotal": output.subtotal,
            "tax_amount": output.tax_amount,
            "total_amount": output.total_amount,
            "lines": lines,
        }
    return {
        "invoice_number": output.invoice_number,
        "po_number": output.po_number,
        "grn_number": output.grn_number,
        "vendor_name": output.vendor_name,
        "lines": lines,
    }
