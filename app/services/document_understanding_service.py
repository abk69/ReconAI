"""Orchestrate deterministic document understanding (M4)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, DocumentExtractionResult
from app.domain.enums import DocumentStatus, DocumentType, ExtractionOutcome
from app.extraction.base import EXTRACTOR_VERSION, select_extractor
from app.extraction.classifier import classify_document
from app.extraction.schemas import ExtractionResultPayload, ValidationResult
from app.extraction.structure import build_candidate
from app.extraction.validator import validate_candidate
from app.services.review_service import ReviewService
from app.storage.base import StorageBackend, StorageError
from app.storage.local import LocalFileStorage


class DocumentUnderstandingError(Exception):
    """Base understanding error."""


class DocumentUnderstandingNotFoundError(DocumentUnderstandingError):
    """Document or extraction result missing."""


class DocumentUnderstandingService:
    """Load stored files, extract, classify, validate, and persist results.

    Never writes into authoritative PO/GRN/Invoice financial tables.
    """

    def __init__(
        self,
        session: Session,
        storage: StorageBackend | None = None,
    ) -> None:
        self._session = session
        settings = get_settings()
        self._storage = storage or LocalFileStorage(settings.storage_root)

    def understand(self, document_id: UUID) -> ExtractionResultPayload:
        document = self._session.get(Document, document_id)
        if document is None:
            raise DocumentUnderstandingNotFoundError(f"Document {document_id} was not found.")

        document.status = DocumentStatus.EXTRACTION_PENDING.value
        self._session.flush()
        document.status = DocumentStatus.EXTRACTING.value
        self._session.flush()

        try:
            data = self._storage.read(stored_filename=document.stored_filename)
        except StorageError as exc:
            return self._finalize(
                document,
                detected_type=DocumentType.UNKNOWN,
                outcome=ExtractionOutcome.EXTRACTION_FAILED,
                message=str(exc),
                validation=ValidationResult(is_valid=False, issues=[]),
                evidence=[],
                candidate=None,
                raw={"error": str(exc)},
            )

        try:
            extractor = select_extractor(document.file_extension, document.mime_type)
        except ValueError as exc:
            return self._finalize(
                document,
                detected_type=DocumentType.UNKNOWN,
                outcome=ExtractionOutcome.EXTRACTION_FAILED,
                message=str(exc),
                validation=ValidationResult(is_valid=False, issues=[]),
                evidence=[],
                candidate=None,
                raw={"error": str(exc)},
            )

        try:
            extracted = extractor.extract(
                document_id=document.id,
                data=data,
                filename=document.original_filename,
                mime_type=document.mime_type,
            )
        except Exception as exc:  # noqa: BLE001
            return self._finalize(
                document,
                detected_type=DocumentType.UNKNOWN,
                outcome=ExtractionOutcome.EXTRACTION_FAILED,
                message=f"Extractor failed: {exc}",
                validation=ValidationResult(is_valid=False, issues=[]),
                evidence=[],
                candidate=None,
                raw={"error": str(exc)},
            )

        document.status = DocumentStatus.EXTRACTED.value
        self._session.flush()

        declared = (
            DocumentType(document.document_type)
            if document.document_type in DocumentType._value2member_map_
            else DocumentType.UNKNOWN
        )
        detected = classify_document(
            extracted,
            declared_type=declared,
            original_filename=document.original_filename,
        )
        extracted.detected_type = detected

        candidate, evidence = build_candidate(extracted, detected)
        document.status = DocumentStatus.NORMALIZED.value
        self._session.flush()

        validation = validate_candidate(
            document_type=detected,
            candidate=candidate,
            extraction_warnings=extracted.warnings,
        )

        if validation.is_valid:
            outcome = ExtractionOutcome.READY_FOR_RECONCILIATION
            message = "Document understood and validated."
        elif validation.requires_review:
            outcome = ExtractionOutcome.REVIEW_REQUIRED
            message = "Extraction requires human review."
        else:
            outcome = ExtractionOutcome.VALIDATION_FAILED
            message = "Extraction failed validation."

        # Optional: update declared document_type when confidently classified.
        if detected is not DocumentType.UNKNOWN and declared is DocumentType.UNKNOWN:
            document.document_type = detected.value

        return self._finalize(
            document,
            detected_type=detected,
            outcome=outcome,
            message=message,
            validation=validation,
            evidence=evidence,
            candidate=candidate.model_dump(mode="json") if candidate else None,
            raw=extracted.model_dump(mode="json"),
        )

    def get_understanding(self, document_id: UUID) -> ExtractionResultPayload:
        document = self._session.get(Document, document_id)
        if document is None:
            raise DocumentUnderstandingNotFoundError(f"Document {document_id} was not found.")
        row = self._session.scalar(
            select(DocumentExtractionResult).where(
                DocumentExtractionResult.document_id == document_id
            )
        )
        if row is None:
            raise DocumentUnderstandingNotFoundError(
                f"No understanding result for document {document_id}."
            )
        return ExtractionResultPayload(
            document_id=document_id,
            detected_type=DocumentType(row.detected_type),
            outcome=ExtractionOutcome(row.outcome),
            document_status=document.status,
            message=row.message,
            candidate=row.candidate,
            validation=ValidationResult.model_validate(row.validation),
            evidence=row.evidence or [],
            raw_extraction=row.raw_extraction or {},
            extractor_version=row.extractor_version,
        )

    def _finalize(
        self,
        document: Document,
        *,
        detected_type: DocumentType,
        outcome: ExtractionOutcome,
        message: str | None,
        validation: ValidationResult,
        evidence: list,
        candidate: dict | None,
        raw: dict,
    ) -> ExtractionResultPayload:
        status_map = {
            ExtractionOutcome.READY_FOR_RECONCILIATION: DocumentStatus.READY_FOR_RECONCILIATION,
            ExtractionOutcome.REVIEW_REQUIRED: DocumentStatus.REVIEW_REQUIRED,
            ExtractionOutcome.VALIDATION_FAILED: DocumentStatus.VALIDATION_FAILED,
            ExtractionOutcome.EXTRACTION_FAILED: DocumentStatus.EXTRACTION_FAILED,
        }
        document.status = status_map[outcome].value

        evidence_payload = [
            e.model_dump(mode="json") if hasattr(e, "model_dump") else e for e in evidence
        ]
        validation_payload = validation.model_dump(mode="json")

        existing = self._session.scalar(
            select(DocumentExtractionResult).where(
                DocumentExtractionResult.document_id == document.id
            )
        )
        if existing is None:
            existing = DocumentExtractionResult(document_id=document.id)
            self._session.add(existing)

        existing.detected_type = detected_type.value
        existing.outcome = outcome.value
        existing.extractor_version = EXTRACTOR_VERSION
        existing.raw_extraction = raw
        existing.candidate = candidate
        existing.validation = validation_payload
        existing.evidence = evidence_payload
        existing.message = message
        self._session.flush()

        # M5: auto-create a review task only when human intervention is required.
        ReviewService(self._session).create_from_extraction_if_needed(
            document=document,
            extraction=existing,
            outcome=outcome,
            validation=validation_payload,
        )
        self._session.commit()

        return ExtractionResultPayload(
            document_id=document.id,
            detected_type=detected_type,
            outcome=outcome,
            document_status=document.status,
            message=message,
            candidate=candidate,
            validation=validation,
            evidence=evidence,
            raw_extraction=raw,
            extractor_version=EXTRACTOR_VERSION,
        )
