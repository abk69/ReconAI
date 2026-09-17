"""Schemas for deterministic extraction evaluation."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DocumentType


class GoldenDocument(BaseModel):
    """Expected structured values for one golden evaluation fixture."""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    document_type: DocumentType
    description: str = ""
    expected: dict[str, Any]
    # Optional raw text / fixture hints for building an actual candidate in tests.
    notes: str | None = None


class FieldEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field_path: str
    expected: Any = None
    actual: Any = None
    status: str  # correct | incorrect | missing | unexpected


class LineItemMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_count: int = 0
    actual_count: int = 0
    count_match: bool = False
    fields_evaluated: int = 0
    fields_correct: int = 0
    field_accuracy: Decimal = Decimal("0")


class EvaluationResult(BaseModel):
    """Structured result answering: how well did extraction perform?"""

    model_config = ConfigDict(extra="forbid")

    evaluation_id: str
    document_type: DocumentType
    fields_evaluated: int = 0
    correct_fields: list[str] = Field(default_factory=list)
    incorrect_fields: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    unexpected_fields: list[str] = Field(default_factory=list)
    field_details: list[FieldEvaluation] = Field(default_factory=list)
    field_accuracy: Decimal = Decimal("0")
    completeness: Decimal = Decimal("0")
    line_item_metrics: LineItemMetrics | None = None
    overall_success: bool = False
    message: str | None = None
