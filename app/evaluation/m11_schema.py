"""Typed ground truth and error records for M11 extraction evaluation."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DocumentType

DATASET_ID = "m11_extraction_eval_v1"


class ErrorCategory(StrEnum):
    MISSING_FIELD = "MISSING_FIELD"
    INCORRECT_FIELD = "INCORRECT_FIELD"
    NORMALIZATION_MISMATCH = "NORMALIZATION_MISMATCH"
    NUMERIC_MISMATCH = "NUMERIC_MISMATCH"
    DATE_MISMATCH = "DATE_MISMATCH"
    MISSING_LINE = "MISSING_LINE"
    EXTRA_LINE = "EXTRA_LINE"
    LINE_FIELD_MISMATCH = "LINE_FIELD_MISMATCH"
    DOCUMENT_TYPE_MISMATCH = "DOCUMENT_TYPE_MISMATCH"
    EMPTY_EXTRACTION = "EMPTY_EXTRACTION"
    UNEXPECTED_FIELD = "UNEXPECTED_FIELD"


class GroundTruthLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_identifier: str | None = None
    description: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    tax_rate: Decimal | None = None
    line_total: Decimal | None = None


class GroundTruth(BaseModel):
    """Expected extraction values. Null means the field is not expected."""

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    vendor_name: str | None = None
    po_number: str | None = None
    invoice_number: str | None = None
    grn_number: str | None = None
    invoice_date: date | None = None
    order_date: date | None = None
    receipt_date: date | None = None
    currency: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    lines: list[GroundTruthLine] = Field(default_factory=list)


class SourceTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sheet: str | None = None
    headers: list[str]
    rows: list[list[str]]


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    document_type: DocumentType
    source_representation: str
    source_text: str
    filename: str
    tables: list[SourceTable] = Field(default_factory=list)
    ground_truth: GroundTruth
    notes: str
    edge_conditions: list[str]


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    field: str
    expected: str | None = None
    predicted: str | None = None
    category: ErrorCategory


class CaseMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    header_expected: int
    header_correct: int
    header_missing: int
    header_incorrect: int
    header_unexpected: int
    header_accuracy: str
    header_accuracy_numerator: int
    header_accuracy_denominator: int
    header_completeness: str
    header_completeness_numerator: int
    header_completeness_denominator: int
    line_expected_count: int
    line_predicted_count: int
    line_count_match: bool
    lines_matched: int
    lines_missing: int
    lines_extra: int
    line_fields_expected: int
    line_fields_correct: int
    line_fields_incorrect: int
    line_accuracy: str
    line_accuracy_numerator: int
    line_accuracy_denominator: int
    line_completeness: str
    line_completeness_numerator: int
    line_completeness_denominator: int
    exact_match: bool
    success: bool


class CaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    document_type: DocumentType
    passed: bool
    metrics: CaseMetrics
    errors: list[FieldError]
