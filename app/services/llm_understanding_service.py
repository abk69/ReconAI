"""LLM-assisted document understanding service (M6).

Orchestrates quality gate → Gemini → validate → evidence → compare → M5.
Never writes authoritative PO/GRN/Invoice rows.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.models import Document, DocumentExtractionResult, LlmExtractionResult
from app.domain.enums import (
    ApplicationQuality,
    DocumentStatus,
    DocumentType,
    LlmInvocationStatus,
    ReviewPriority,
)
from app.extraction.schemas import (
    GoodsReceiptCandidate,
    InvoiceCandidate,
    PurchaseOrderCandidate,
)
from app.extraction.validator import validate_candidate
from app.llm.base import LLMProvider, LLMProviderError
from app.llm.comparison import compare_candidates
from app.llm.evidence import validate_evidence
from app.llm.extractor import (
    build_document_text_from_raw,
    coerce_document_type,
    gemini_evidence_to_field_evidence,
    tables_from_raw,
)
from app.llm.gemini import GeminiProvider
from app.llm.prompts import SYSTEM_INSTRUCTION, build_user_content, summarize_tables
from app.llm.quality import assess_application_quality
from app.llm.quality_gate import evaluate_quality_gate
from app.llm.schemas import PROMPT_VERSION, gemini_output_to_candidate
from app.services.review_service import ReviewService


class LlmUnderstandingError(Exception):
    """Base M6 service error."""


class LlmUnderstandingNotFoundError(LlmUnderstandingError):
    """Document or LLM result missing."""


class LlmUnderstandingService:
    """Run gated Gemini assistance against an existing M4 extraction."""

    def __init__(
        self,
        session: Session,
        *,
        provider: LLMProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._provider = provider or GeminiProvider(self._settings)

    def understand(self, document_id: UUID) -> LlmExtractionResult:
        document = self._session.get(Document, document_id)
        if document is None:
            raise LlmUnderstandingNotFoundError(f"Document {document_id} was not found.")

        m4 = self._session.scalar(
            select(DocumentExtractionResult).where(
                DocumentExtractionResult.document_id == document_id
            )
        )
        if m4 is None:
            raise LlmUnderstandingNotFoundError(
                f"No M4 understanding result for document {document_id}. "
                "Run POST /documents/{id}/understand first."
            )

        gate = evaluate_quality_gate(
            outcome=m4.outcome,
            detected_type=m4.detected_type,
            validation=m4.validation if isinstance(m4.validation, dict) else {},
            candidate=m4.candidate if isinstance(m4.candidate, dict) else None,
        )

        if not gate.should_invoke:
            row = self._persist(
                document=document,
                m4=m4,
                invocation_status=LlmInvocationStatus.SKIPPED_M4_SUFFICIENT,
                gate_reasons=gate.reasons,
                message="M4 result is sufficient; Gemini was not called.",
                application_quality=ApplicationQuality.HIGH,
                quality_reasons=gate.reasons,
            )
            self._session.commit()
            return row

        document_text = build_document_text_from_raw(
            m4.raw_extraction if isinstance(m4.raw_extraction, dict) else {}
        )
        tables = tables_from_raw(m4.raw_extraction if isinstance(m4.raw_extraction, dict) else {})
        tables_text = summarize_tables(tables)
        m4_context = {
            "detected_type": m4.detected_type,
            "outcome": m4.outcome,
            "validation_issues": [
                i.get("code")
                for i in (m4.validation or {}).get("issues", [])
                if isinstance(i, dict)
            ],
        }
        user_content = build_user_content(
            document_text=document_text,
            tables_summary=tables_text or None,
            m4_context=m4_context,
            max_chars=self._settings.llm_max_input_chars,
        )

        try:
            llm_response = self._provider.extract_structured(
                system_instruction=SYSTEM_INSTRUCTION,
                user_content=user_content,
            )
        except LLMProviderError as exc:
            row = self._persist(
                document=document,
                m4=m4,
                invocation_status=LlmInvocationStatus.PROVIDER_ERROR,
                gate_reasons=gate.reasons,
                message="Gemini unavailable or failed; human review required.",
                application_quality=ApplicationQuality.REVIEW_REQUIRED,
                quality_reasons=[str(exc)],
                error_code=exc.code,
                error_message=str(exc),
            )
            self._ensure_review(
                document,
                m4,
                reason=f"Gemini provider error ({exc.code}): {exc}",
                priority=ReviewPriority.HIGH,
            )
            document.status = DocumentStatus.REVIEW_REQUIRED.value
            self._session.commit()
            return row

        output = llm_response.output
        candidate = gemini_output_to_candidate(output)
        detected = coerce_document_type(output.document_type)

        # Business validation via existing M4 validator.
        typed_candidate = _hydrate_candidate(detected, candidate)
        validation = validate_candidate(
            document_type=detected,
            candidate=typed_candidate,
            extraction_warnings=[],
        )
        validation_payload = validation.model_dump(mode="json")
        hard_errors = any(i.severity == "error" for i in validation.issues)
        business_ok = validation.is_valid and not hard_errors

        evidence_check = validate_evidence(
            output,
            document_text=document_text,
            tables_text=tables_text,
        )
        comparison = compare_candidates(
            m4.candidate if isinstance(m4.candidate, dict) else None,
            candidate,
        )
        quality = assess_application_quality(
            structured_valid=True,
            business_validation_ok=business_ok,
            evidence=evidence_check,
            comparison=comparison,
        )

        invocation = LlmInvocationStatus.INVOKED
        if not evidence_check.is_grounded:
            invocation = LlmInvocationStatus.EVIDENCE_FAILED
        elif hard_errors:
            invocation = LlmInvocationStatus.VALIDATION_FAILED
        elif comparison.has_financial_disagreement:
            invocation = LlmInvocationStatus.DISAGREEMENT

        field_evidence = gemini_evidence_to_field_evidence(output)
        usage = {
            "input_tokens": llm_response.usage.input_tokens,
            "output_tokens": llm_response.usage.output_tokens,
            "total_tokens": llm_response.usage.total_tokens,
        }

        # Trust boundary: Gemini never auto-promotes; always queue human review
        # when Gemini was invoked because M4 was insufficient.
        document.status = DocumentStatus.REVIEW_REQUIRED.value
        priority = ReviewPriority.MEDIUM
        if comparison.has_financial_disagreement or not evidence_check.is_grounded:
            priority = ReviewPriority.HIGH
        elif quality.quality is ApplicationQuality.HIGH:
            priority = ReviewPriority.LOW
        reason = "; ".join(quality.reasons[:5]) or "Gemini-assisted extraction needs human review."
        self._ensure_review(document, m4, reason=reason, priority=priority)

        row = self._persist(
            document=document,
            m4=m4,
            invocation_status=invocation,
            gate_reasons=gate.reasons,
            message="Gemini-assisted extraction completed.",
            application_quality=quality.quality,
            quality_reasons=quality.reasons,
            candidate=candidate,
            evidence=[e.model_dump(mode="json") for e in field_evidence],
            validation=validation_payload,
            comparison=comparison.to_dict(),
            evidence_check={
                "is_grounded": evidence_check.is_grounded,
                "unsupported_fields": evidence_check.unsupported_fields,
                "details": evidence_check.details,
            },
            usage=usage,
            provider_metadata=llm_response.provider_metadata,
            model=llm_response.model,
            provider=llm_response.provider,
        )
        self._session.commit()
        return row

    def get_latest(self, document_id: UUID) -> LlmExtractionResult:
        row = self._session.scalar(
            select(LlmExtractionResult)
            .where(LlmExtractionResult.document_id == document_id)
            .order_by(LlmExtractionResult.created_at.desc())
        )
        if row is None:
            raise LlmUnderstandingNotFoundError(
                f"No LLM understanding result for document {document_id}."
            )
        return row

    def _ensure_review(
        self,
        document: Document,
        m4: DocumentExtractionResult,
        *,
        reason: str,
        priority: ReviewPriority,
    ) -> None:
        """Create/update M5 review task. Does not overwrite M4 candidate."""
        reviews = ReviewService(self._session)
        task = reviews.create_review_task(
            document_id=document.id,
            extraction_result_id=m4.id,
            reason=reason,
            priority=priority,
            commit=False,
        )
        task.reason = reason
        task.priority = priority.value
        self._session.flush()

    def _persist(
        self,
        *,
        document: Document,
        m4: DocumentExtractionResult,
        invocation_status: LlmInvocationStatus,
        gate_reasons: list[str],
        message: str,
        application_quality: ApplicationQuality | None = None,
        quality_reasons: list[str] | None = None,
        candidate: dict[str, Any] | None = None,
        evidence: list[Any] | None = None,
        validation: dict[str, Any] | None = None,
        comparison: dict[str, Any] | None = None,
        evidence_check: dict[str, Any] | None = None,
        usage: dict[str, Any] | None = None,
        provider_metadata: dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        model: str | None = None,
        provider: str | None = None,
    ) -> LlmExtractionResult:
        row = LlmExtractionResult(
            document_id=document.id,
            m4_extraction_result_id=m4.id,
            provider=provider or self._settings.llm_provider,
            model=model or self._settings.llm_model,
            prompt_version=PROMPT_VERSION,
            invocation_status=invocation_status.value,
            application_quality=(
                application_quality.value if application_quality is not None else None
            ),
            quality_reasons=quality_reasons or [],
            gate_reasons=gate_reasons,
            candidate=candidate,
            evidence=evidence or [],
            validation=validation or {},
            comparison=comparison,
            evidence_check=evidence_check,
            usage=usage,
            provider_metadata=provider_metadata or {},
            error_code=error_code,
            error_message=error_message,
            message=message,
        )
        self._session.add(row)
        self._session.flush()
        return row


def _hydrate_candidate(
    document_type: DocumentType,
    candidate: dict[str, Any],
) -> PurchaseOrderCandidate | GoodsReceiptCandidate | InvoiceCandidate | None:
    try:
        if document_type is DocumentType.PO:
            return PurchaseOrderCandidate.model_validate(candidate)
        if document_type is DocumentType.GRN:
            return GoodsReceiptCandidate.model_validate(candidate)
        if document_type is DocumentType.INVOICE:
            return InvoiceCandidate.model_validate(candidate)
    except Exception:  # noqa: BLE001
        return None
    return None
