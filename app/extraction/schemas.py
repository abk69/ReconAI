"""Pydantic schemas for raw extraction, candidates, evidence, and validation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DocumentType, ExtractionOutcome, FieldConfidence


class FieldEvidence(BaseModel):
    """Provenance for an extracted field (deterministic confidence, not ML)."""

    model_config = ConfigDict(extra="forbid")

    field_name: str
    value: Any = None
    raw_value: str | None = None
    source_type: str
    page: int | None = None
    sheet: str | None = None
    cell: str | None = None
    source_text: str | None = None
    extraction_method: str
    confidence: FieldConfidence
    reason: str | None = None


class TextBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    page: int | None = None
    sheet: str | None = None
    cell: str | None = None
    source_type: str = "text"


class TableCell(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row: int
    column: int
    value: str
    cell_ref: str | None = None


class ExtractedTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet: str | None = None
    page: int | None = None
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)


class ExtractedDocument(BaseModel):
    """Canonical raw representation before structured domain mapping."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    detected_type: DocumentType = DocumentType.UNKNOWN
    pages: list[str] = Field(default_factory=list)
    text_blocks: list[TextBlock] = Field(default_factory=list)
    tables: list[ExtractedTable] = Field(default_factory=list)
    full_text: str = ""
    extractor_name: str
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CandidateLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_number: int | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None
    reference: str | None = None
    evidence: list[FieldEvidence] = Field(default_factory=list)


class PurchaseOrderCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    po_number: str | None = None
    vendor_name: str | None = None
    order_date: date | None = None
    currency: str | None = None
    lines: list[CandidateLine] = Field(default_factory=list)
    evidence: list[FieldEvidence] = Field(default_factory=list)


class GoodsReceiptCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grn_number: str | None = None
    po_number: str | None = None
    receipt_date: date | None = None
    vendor_name: str | None = None
    lines: list[CandidateLine] = Field(default_factory=list)
    evidence: list[FieldEvidence] = Field(default_factory=list)


class InvoiceCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invoice_number: str | None = None
    po_number: str | None = None
    vendor_name: str | None = None
    invoice_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    lines: list[CandidateLine] = Field(default_factory=list)
    evidence: list[FieldEvidence] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    field_name: str | None = None
    severity: str = "error"


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    requires_review: bool = False
    issues: list[ValidationIssue] = Field(default_factory=list)


class ExtractionResultPayload(BaseModel):
    """Full understanding result returned by the service/API."""

    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    detected_type: DocumentType
    outcome: ExtractionOutcome
    document_status: str
    message: str | None = None
    candidate: dict[str, Any] | None = None
    validation: ValidationResult
    evidence: list[FieldEvidence] = Field(default_factory=list)
    raw_extraction: dict[str, Any] = Field(default_factory=dict)
    extractor_version: str = "m4-1.0"
