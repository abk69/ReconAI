"""Policy grounding service (M7.4) — RAG explanation only; M2 remains financial truth."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import Settings, get_settings
from app.db.models import (
    Invoice,
    PolicyGroundingResult,
    PolicyVersion,
    PurchaseOrder,
    ReconciliationException,
)
from app.domain.enums import PolicyVersionStatus
from app.embeddings.base import EmbeddingProvider
from app.llm.base import LLMProvider, LLMProviderError, StructuredLLMResponse
from app.llm.gemini import GeminiProvider
from app.llm.grounding_prompts import (
    SYSTEM_INSTRUCTION,
    build_grounding_user_content,
    build_retrieval_query,
    evidence_block_from_hit,
)
from app.llm.grounding_schemas import (
    GroundedPolicyGeminiOutput,
    GroundedPolicyResponse,
    PolicyCitation,
    PolicyGroundingStatus,
)
from app.services.policy_retrieval_service import PolicyRetrievalService, RetrievalHit


class PolicyGroundingError(Exception):
    """Base grounding error."""


class PolicyGroundingNotFoundError(PolicyGroundingError):
    """Exception or related entity missing."""


class PolicyGroundingValidationError(PolicyGroundingError):
    """Invalid grounding input or fabricated citations."""


@dataclass
class _VersionMeta:
    version_label: str
    status: str
    effective_from: Any
    effective_to: Any
    policy_document_id: UUID


class PolicyGroundingService:
    """Retrieve policy evidence and produce a grounded Gemini explanation.

    Never mutates reconciliation exception status or financial tables.
    Optional persistence writes an AI-derived audit row only.
    """

    def __init__(
        self,
        session: Session,
        *,
        llm: LLMProvider | None = None,
        retrieval: PolicyRetrievalService | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._settings = settings or get_settings()
        self._llm = llm or GeminiProvider(self._settings)
        self._retrieval = retrieval or PolicyRetrievalService(
            session,
            provider=embedding_provider,
            settings=self._settings,
        )

    def explain_exception(
        self,
        exception_id: UUID,
        *,
        policy_version_id: UUID | None = None,
        policy_document_id: UUID | None = None,
        top_k: int | None = None,
        persist: bool = True,
    ) -> GroundedPolicyResponse:
        exc = self._load_exception(exception_id)
        original_status = exc.status
        facts = self._build_facts(exc)
        query = build_retrieval_query(facts)
        k = top_k or self._settings.policy_grounding_top_k

        hits = self._retrieval.retrieve_policy_chunks(
            query,
            top_k=k,
            policy_document_id=policy_document_id,
            policy_version_id=policy_version_id,
        )
        relevant = self._filter_relevant(hits)
        version_meta = self._load_version_meta(relevant)

        if not relevant:
            response = self._insufficient(
                exception_id=exception_id,
                query=query,
                reason=(
                    "No sufficiently relevant policy evidence was retrieved "
                    f"(min similarity {self._settings.policy_retrieval_min_similarity})."
                ),
                retrieved=[],
            )
            return self._maybe_persist(exc, response, facts, persist, original_status)

        conflict = self._detect_version_conflict(relevant, version_meta)
        if conflict is not None:
            response = conflict
            response = GroundedPolicyResponse(
                exception_id=exception_id,
                status=PolicyGroundingStatus.CONFLICTING_POLICY,
                conclusion=conflict.conclusion,
                explanation=conflict.explanation,
                policy_support=conflict.policy_support,
                citations=self._citations_for_hits(relevant, version_meta),
                limitations=conflict.limitations,
                retrieval_query=query,
                retrieved_chunk_ids=[h.chunk_id for h in relevant],
                model=None,
            )
            return self._maybe_persist(exc, response, facts, persist, original_status)

        try:
            gemini_out, llm_meta = self._call_gemini(facts, relevant, version_meta)
            response = self._validate_and_build(
                exception_id=exception_id,
                query=query,
                hits=relevant,
                version_meta=version_meta,
                gemini_out=gemini_out,
                model=llm_meta.model,
            )
        except LLMProviderError as exc_err:
            response = GroundedPolicyResponse(
                exception_id=exception_id,
                status=PolicyGroundingStatus.PROVIDER_ERROR,
                conclusion="Policy explanation unavailable due to provider failure.",
                explanation=str(exc_err),
                policy_support="",
                citations=[],
                limitations=f"provider_code={exc_err.code}",
                retrieval_query=query,
                retrieved_chunk_ids=[h.chunk_id for h in relevant],
                model=getattr(self._llm, "model", None),
            )
        except PolicyGroundingValidationError as exc_err:
            response = GroundedPolicyResponse(
                exception_id=exception_id,
                status=PolicyGroundingStatus.INSUFFICIENT_EVIDENCE,
                conclusion="Grounded explanation rejected due to invalid citations.",
                explanation=str(exc_err),
                policy_support="",
                citations=[],
                limitations="Fabricated or unknown citation IDs were rejected.",
                retrieval_query=query,
                retrieved_chunk_ids=[h.chunk_id for h in relevant],
                model=getattr(self._llm, "model", None),
            )

        return self._maybe_persist(exc, response, facts, persist, original_status)

    def _load_exception(self, exception_id: UUID) -> ReconciliationException:
        exc = self._session.scalar(
            select(ReconciliationException)
            .where(ReconciliationException.id == exception_id)
            .options(
                joinedload(ReconciliationException.purchase_order).joinedload(
                    PurchaseOrder.vendor
                ),
                joinedload(ReconciliationException.invoice).joinedload(Invoice.vendor),
                joinedload(ReconciliationException.goods_receipt),
            )
        )
        if exc is None:
            raise PolicyGroundingNotFoundError(
                f"Reconciliation exception {exception_id} was not found."
            )
        return exc

    def _build_facts(self, exc: ReconciliationException) -> dict[str, Any]:
        po = exc.purchase_order
        inv = exc.invoice
        grn = exc.goods_receipt
        vendor_name = None
        if po is not None and po.vendor is not None:
            vendor_name = po.vendor.name
        elif inv is not None and inv.vendor is not None:
            vendor_name = inv.vendor.name

        return {
            "exception_id": str(exc.id),
            "exception_type": exc.exception_type,
            "severity": exc.severity,
            "message": exc.message,
            "exception_status": exc.status,
            "po_number": po.po_number if po else None,
            "invoice_number": inv.invoice_number if inv else None,
            "grn_number": grn.grn_number if grn else None,
            "vendor": vendor_name,
            "purchase_order_id": str(exc.purchase_order_id) if exc.purchase_order_id else None,
            "invoice_id": str(exc.invoice_id) if exc.invoice_id else None,
            "goods_receipt_id": str(exc.goods_receipt_id) if exc.goods_receipt_id else None,
            "evidence": dict(exc.evidence or {}),
            "note": (
                "These facts were produced by deterministic M2 reconciliation. "
                "Do not recalculate or override them."
            ),
        }

    def _filter_relevant(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        threshold = self._settings.policy_retrieval_min_similarity
        return [h for h in hits if h.similarity >= threshold]

    def _load_version_meta(self, hits: list[RetrievalHit]) -> dict[UUID, _VersionMeta]:
        ids = {h.policy_version_id for h in hits}
        meta: dict[UUID, _VersionMeta] = {}
        for vid in ids:
            version = self._session.get(PolicyVersion, vid)
            if version is None:
                continue
            meta[vid] = _VersionMeta(
                version_label=version.version_label,
                status=version.status,
                effective_from=version.effective_from,
                effective_to=version.effective_to,
                policy_document_id=version.policy_document_id,
            )
        return meta

    def _detect_version_conflict(
        self,
        hits: list[RetrievalHit],
        version_meta: dict[UUID, _VersionMeta],
    ) -> GroundedPolicyResponse | None:
        """Same policy document with multiple applicable versions in evidence → conflict.

        Does not invent precedence; surfaces CONFLICTING_POLICY for the caller.
        """
        by_doc: dict[UUID, set[UUID]] = {}
        for hit in hits:
            meta = version_meta.get(hit.policy_version_id)
            if meta is None:
                continue
            # Consider ACTIVE (and DRAFT only if alone) — conflict when 2+ ACTIVE versions.
            if meta.status != PolicyVersionStatus.ACTIVE.value:
                continue
            by_doc.setdefault(meta.policy_document_id, set()).add(hit.policy_version_id)

        conflicting_docs = {doc: vids for doc, vids in by_doc.items() if len(vids) > 1}
        if not conflicting_docs:
            return None

        labels: list[str] = []
        for vids in conflicting_docs.values():
            for vid in sorted(vids, key=str):
                m = version_meta[vid]
                labels.append(f"{m.version_label} ({vid})")

        return GroundedPolicyResponse(
            exception_id=UUID(int=0),  # placeholder overwritten by caller
            status=PolicyGroundingStatus.CONFLICTING_POLICY,
            conclusion="Multiple active policy versions apply; precedence is undefined.",
            explanation=(
                "Retrieved evidence includes more than one ACTIVE version of the same "
                "policy document. ReconAI does not invent precedence rules. "
                f"Versions involved: {', '.join(labels)}."
            ),
            policy_support="",
            citations=[],
            limitations="Resolve which policy version is authoritative, then re-run.",
            retrieval_query="",
            retrieved_chunk_ids=[],
        )

    def _call_gemini(
        self,
        facts: dict[str, Any],
        hits: list[RetrievalHit],
        version_meta: dict[UUID, _VersionMeta],
    ) -> tuple[GroundedPolicyGeminiOutput, StructuredLLMResponse]:
        blocks = [
            evidence_block_from_hit(
                h,
                version_label=version_meta[h.policy_version_id].version_label
                if h.policy_version_id in version_meta
                else "unknown",
            )
            for h in hits
        ]
        allowed = [str(h.chunk_id) for h in hits]
        user_content = build_grounding_user_content(
            reconciliation_facts=facts,
            evidence_blocks=blocks,
            allowed_chunk_ids=allowed,
            max_chars=self._settings.llm_max_input_chars,
        )
        structured = self._llm.generate_structured(
            system_instruction=SYSTEM_INSTRUCTION,
            user_content=user_content,
            response_model=GroundedPolicyGeminiOutput,
        )
        output = structured.output
        if not isinstance(output, GroundedPolicyGeminiOutput):
            output = GroundedPolicyGeminiOutput.model_validate(output)
        return output, structured

    def _validate_and_build(
        self,
        *,
        exception_id: UUID,
        query: str,
        hits: list[RetrievalHit],
        version_meta: dict[UUID, _VersionMeta],
        gemini_out: GroundedPolicyGeminiOutput,
        model: str,
    ) -> GroundedPolicyResponse:
        allow = {h.chunk_id: h for h in hits}
        citations: list[PolicyCitation] = []
        for raw_id in gemini_out.cited_chunk_ids:
            try:
                cid = UUID(str(raw_id))
            except ValueError as exc:
                raise PolicyGroundingValidationError(
                    f"Invalid citation chunk_id {raw_id!r}."
                ) from exc
            hit = allow.get(cid)
            if hit is None:
                raise PolicyGroundingValidationError(
                    f"Citation chunk_id {cid} was not in the retrieved evidence set."
                )
            meta = version_meta.get(hit.policy_version_id)
            citations.append(
                PolicyCitation(
                    policy_document_id=hit.policy_document_id,
                    policy_version_id=hit.policy_version_id,
                    policy_version_label=meta.version_label if meta else "unknown",
                    chunk_id=hit.chunk_id,
                    chunk_index=hit.chunk_index,
                    section_id=hit.section_id,
                    section_title=hit.section_title,
                    source_filename=hit.source_filename,
                    page_number=hit.page_number,
                    content_hash=hit.content_hash,
                    similarity=hit.similarity,
                )
            )

        status = PolicyGroundingStatus(gemini_out.status)
        # If model claims SUPPORTED but cites nothing while we required evidence — downgrade.
        if status == PolicyGroundingStatus.SUPPORTED and not citations:
            status = PolicyGroundingStatus.INSUFFICIENT_EVIDENCE
            limitations = (
                (gemini_out.limitations + " ").strip()
                + "SUPPORTED without citations was downgraded to INSUFFICIENT_EVIDENCE."
            ).strip()
        else:
            limitations = gemini_out.limitations

        return GroundedPolicyResponse(
            exception_id=exception_id,
            status=status,
            conclusion=gemini_out.conclusion,
            explanation=gemini_out.explanation,
            policy_support=gemini_out.policy_support,
            citations=citations,
            limitations=limitations,
            retrieval_query=query,
            retrieved_chunk_ids=[h.chunk_id for h in hits],
            model=model,
        )

    def _citations_for_hits(
        self,
        hits: list[RetrievalHit],
        version_meta: dict[UUID, _VersionMeta],
    ) -> list[PolicyCitation]:
        out: list[PolicyCitation] = []
        for hit in hits:
            meta = version_meta.get(hit.policy_version_id)
            out.append(
                PolicyCitation(
                    policy_document_id=hit.policy_document_id,
                    policy_version_id=hit.policy_version_id,
                    policy_version_label=meta.version_label if meta else "unknown",
                    chunk_id=hit.chunk_id,
                    chunk_index=hit.chunk_index,
                    section_id=hit.section_id,
                    section_title=hit.section_title,
                    source_filename=hit.source_filename,
                    page_number=hit.page_number,
                    content_hash=hit.content_hash,
                    similarity=hit.similarity,
                )
            )
        return out

    def _insufficient(
        self,
        *,
        exception_id: UUID,
        query: str,
        reason: str,
        retrieved: list[RetrievalHit],
    ) -> GroundedPolicyResponse:
        return GroundedPolicyResponse(
            exception_id=exception_id,
            status=PolicyGroundingStatus.INSUFFICIENT_EVIDENCE,
            conclusion="Insufficient policy evidence to form a grounded explanation.",
            explanation=reason,
            policy_support="",
            citations=[],
            limitations="Gemini was not asked to answer from general knowledge.",
            retrieval_query=query,
            retrieved_chunk_ids=[h.chunk_id for h in retrieved],
            model=None,
        )

    def _maybe_persist(
        self,
        exc: ReconciliationException,
        response: GroundedPolicyResponse,
        facts: dict[str, Any],
        persist: bool,
        original_status: str,
    ) -> GroundedPolicyResponse:
        # Invariant: never mutate the exception.
        if exc.status != original_status:
            exc.status = original_status
        self._session.flush()

        if not persist:
            return response

        row = PolicyGroundingResult(
            reconciliation_exception_id=exc.id,
            status=response.status.value,
            conclusion=response.conclusion,
            explanation=response.explanation,
            policy_support=response.policy_support,
            limitations=response.limitations,
            citations=[c.model_dump(mode="json") for c in response.citations],
            retrieved_chunk_ids=[str(i) for i in response.retrieved_chunk_ids],
            retrieval_query=response.retrieval_query,
            model=response.model,
            provider_metadata={"reconciliation_facts_snapshot": facts},
        )
        self._session.add(row)
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        response.grounding_result_id = row.id
        return response
