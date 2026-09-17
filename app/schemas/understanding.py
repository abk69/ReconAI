"""API schemas for document understanding responses."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DocumentType, ExtractionOutcome
from app.extraction.schemas import FieldEvidence, ValidationResult


class UnderstandingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: UUID
    detected_type: DocumentType
    outcome: ExtractionOutcome
    document_status: str
    message: str | None = None
    candidate: dict[str, Any] | None = None
    validation: ValidationResult
    evidence: list[FieldEvidence] = Field(default_factory=list)
    extractor_version: str
    # Intentionally omit raw_extraction filesystem details / full dump by default size;
    # include a compact summary flag.
    has_raw_extraction: bool = True
