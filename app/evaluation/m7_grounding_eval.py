"""M7.5 grounding / citation / abstention evaluator (offline, fake LLM)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ReconciliationException
from app.domain.enums import ExceptionSeverity, ExceptionStatus, ExceptionType
from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_corpus import EvalCorpus, resolve_expected_chunk_ids, seed_eval_corpus
from app.evaluation.m7_golden import DATASET_ID, EVAL_CASES, EvaluationCase
from app.evaluation.m7_metrics import (
    answer_fact_accuracy,
    citation_precision,
    citation_recall,
    mean_defined,
)
from app.llm.base import LLMUsageMetadata, StructuredLLMResponse
from app.llm.grounding_schemas import GroundedPolicyGeminiOutput, PolicyGroundingStatus
from app.services.policy_grounding_service import PolicyGroundingService
from app.services.policy_retrieval_service import PolicyRetrievalService, RetrievalHit
from app.services.policy_service import PolicyService


class FakeGroundingLLM:
    """Deterministic structured LLM driven by an evaluation grounding_mode."""

    def __init__(
        self,
        mode: str,
        *,
        fact_blob: str = "",
        prefer_cite: list[UUID] | None = None,
    ) -> None:
        self.mode = mode
        self.fact_blob = fact_blob
        self.prefer_cite = prefer_cite or []
        self.calls = 0
        self.model = "fake-grounding-eval"

    def generate_structured(self, *, system_instruction, user_content, response_model):
        self.calls += 1
        allow = _parse_allowlist(user_content)
        allow_set = set(allow)
        preferred = [str(c) for c in self.prefer_cite if str(c) in allow_set]
        cite = preferred[:1] or allow[:1]
        if self.mode == "fabricated_citation":
            output = GroundedPolicyGeminiOutput(
                status="SUPPORTED",
                conclusion="Fabricated cite.",
                explanation=self.fact_blob or "explanation",
                policy_support=self.fact_blob,
                cited_chunk_ids=[str(uuid4())],
                limitations="",
            )
        elif self.mode == "zero_citation_supported":
            output = GroundedPolicyGeminiOutput(
                status="SUPPORTED",
                conclusion="Claim without cites.",
                explanation=self.fact_blob or "explanation",
                policy_support=self.fact_blob,
                cited_chunk_ids=[],
                limitations="",
            )
        else:
            output = GroundedPolicyGeminiOutput(
                status="SUPPORTED",
                conclusion=f"Policy supports the facts. {self.fact_blob}",
                explanation=f"Based on retrieved evidence. {self.fact_blob}",
                policy_support=self.fact_blob,
                cited_chunk_ids=cite,
                limitations="",
            )
        return StructuredLLMResponse(
            output=output,
            raw_text=None,
            model=self.model,
            provider="fake",
            usage=LLMUsageMetadata(),
        )

    def extract_structured(self, *, system_instruction, user_content):
        raise NotImplementedError


def _parse_allowlist(user_content: str) -> list[str]:
    match = re.search(
        r"CITATION ALLOWLIST \(cite ONLY these chunk_id values\) ===\n(\[.*?\])",
        user_content,
        re.S,
    )
    if not match:
        # Fallback: any JSON list of UUID-looking strings after ALLOWLIST
        match = re.search(r"ALLOWLIST[^\n]*\n(\[[^\]]+\])", user_content, re.S)
    if not match:
        return []
    try:
        return [str(x) for x in json.loads(match.group(1))]
    except json.JSONDecodeError:
        return []


def _facts_blob(facts: dict[str, str]) -> str:
    return " ".join(f"{k}={v}" for k, v in facts.items())


@dataclass
class GroundingCaseResult:
    case_id: str
    category: str
    expected_status: str | None
    actual_status: str
    status_match: bool
    citation_precision: float | None
    citation_recall: float | None
    answer_fact_accuracy: float | None
    gemini_calls: int
    notes: str = ""


class PolicyGroundingEvaluator:
    """Evaluate M7.4 grounding behavior with deterministic fake LLM responses."""

    def __init__(
        self,
        session: Session,
        *,
        corpus: EvalCorpus | None = None,
        embedding_provider: FakeEmbeddingProvider | None = None,
    ) -> None:
        self._session = session
        self._provider = embedding_provider or FakeEmbeddingProvider(
            model="fake-embedding-eval",
            dimension=768,
        )
        self._corpus = corpus or seed_eval_corpus(session, embedding_provider=self._provider)

    @property
    def corpus(self) -> EvalCorpus:
        return self._corpus

    def evaluate_case(self, case: EvaluationCase) -> GroundingCaseResult:
        mode = case.grounding_mode or "supported_cite_relevant"
        expected_chunks = resolve_expected_chunk_ids(
            self._corpus,
            policy_key=case.policy_key,
            section_ids=case.expected_section_ids,
            content_markers=case.expected_content_markers,
            session=self._session,
        )
        exc = self._seed_exception()
        llm = FakeGroundingLLM(
            mode,
            fact_blob=_facts_blob(case.expected_answer_facts),
            prefer_cite=list(expected_chunks),
        )
        settings, retrieval = self._build_retrieval(case, mode)

        svc = PolicyGroundingService(
            self._session,
            llm=llm,  # type: ignore[arg-type]
            retrieval=retrieval,
            settings=settings,
        )
        version_id = None
        if case.policy_key and case.policy_key in self._corpus.policies:
            version_id = self._corpus.policies[case.policy_key].policy_version_id

        result = svc.explain_exception(
            exc.id,
            policy_version_id=version_id,
            persist=False,
        )

        cited = {c.chunk_id for c in result.citations}
        retrieved = set(result.retrieved_chunk_ids)
        text = " ".join(
            [result.conclusion, result.explanation, result.policy_support, result.limitations]
        )
        prec = citation_precision(cited, retrieved)
        # For fabricated cites rejected to INSUFFICIENT with empty citations,
        # precision is undefined (None) — that is correct.
        if mode == "fabricated_citation" and not cited:
            prec = None
        recall = citation_recall(cited, expected_chunks)
        facts_acc = answer_fact_accuracy(case.expected_answer_facts, text)
        if result.status != PolicyGroundingStatus.SUPPORTED:
            # Fact accuracy only scored for supported answers.
            facts_acc = None if case.expected_status != "SUPPORTED" else facts_acc

        expected_status = case.expected_status
        actual = result.status.value
        return GroundingCaseResult(
            case_id=case.id,
            category=case.category.value,
            expected_status=expected_status,
            actual_status=actual,
            status_match=expected_status == actual if expected_status else True,
            citation_precision=prec,
            citation_recall=recall,
            answer_fact_accuracy=facts_acc if expected_status == "SUPPORTED" else None,
            gemini_calls=llm.calls,
            notes=case.notes,
        )

    def evaluate(
        self,
        cases: list[EvaluationCase] | None = None,
    ) -> dict[str, Any]:
        pool = [c for c in (cases or EVAL_CASES) if c.expected_status is not None]
        results = [self.evaluate_case(c) for c in pool]

        abstention_cases = [
            r
            for r in results
            if r.expected_status == PolicyGroundingStatus.INSUFFICIENT_EVIDENCE.value
        ]
        abstention_correct = sum(1 for r in abstention_cases if r.status_match)
        abstention_acc = (
            abstention_correct / len(abstention_cases) if abstention_cases else None
        )

        supported = [r for r in results if r.expected_status == "SUPPORTED"]
        return {
            "dataset": DATASET_ID,
            "cases": len(results),
            "grounding": {
                "citation_precision": mean_defined([r.citation_precision for r in results]),
                "citation_recall": mean_defined([r.citation_recall for r in supported]),
                "answer_fact_accuracy": mean_defined(
                    [r.answer_fact_accuracy for r in supported]
                ),
                "abstention_accuracy": abstention_acc,
                "status_match_rate": (
                    sum(1 for r in results if r.status_match) / len(results) if results else None
                ),
            },
            "case_results": [asdict(r) for r in results],
        }

    def _seed_exception(self) -> ReconciliationException:
        exc = ReconciliationException(
            exception_type=ExceptionType.PRICE_MISMATCH.value,
            severity=ExceptionSeverity.HIGH.value,
            message="Unit price variance between PO and invoice.",
            status=ExceptionStatus.OPEN.value,
            evidence={
                "expected_unit_price": "100.00",
                "billed_unit_price": "105.00",
                "percentage_variance": "5.0",
            },
            fingerprint=f"eval-{uuid4().hex}",
            source_document_ids=[],
        )
        self._session.add(exc)
        self._session.commit()
        return exc

    def _build_retrieval(
        self,
        case: EvaluationCase,
        mode: str,
    ) -> tuple[Settings, PolicyRetrievalService]:
        if mode in {"insufficient_high_threshold", "insufficient_no_call"}:
            settings = Settings(
                policy_retrieval_min_similarity=0.999,
                policy_grounding_top_k=case.top_k,
                embedding_dimension=768,
            )
            return settings, PolicyRetrievalService(
                self._session, provider=self._provider, settings=settings
            )

        if mode == "insufficient_empty_kb":
            settings = Settings(
                policy_retrieval_min_similarity=0.01,
                policy_grounding_top_k=case.top_k,
                embedding_dimension=768,
            )

            class EmptyRetrieval(PolicyRetrievalService):
                def retrieve_policy_chunks(self, *args, **kwargs):
                    return []

            return settings, EmptyRetrieval(
                self._session, provider=self._provider, settings=settings
            )

        if mode == "conflict" or case.force_conflict:
            settings = Settings(
                policy_retrieval_min_similarity=0.01,
                policy_grounding_top_k=5,
                embedding_dimension=768,
            )
            v1 = self._corpus.policies["price_v2026_1"]
            v2 = self._corpus.policies["price_v2026_2"]
            session = self._session

            class DualRetrieval(PolicyRetrievalService):
                def retrieve_policy_chunks(
                    self,
                    query,
                    *,
                    top_k=5,
                    policy_document_id=None,
                    policy_version_id=None,
                ):
                    hits: list[RetrievalHit] = []
                    for seeded in (v1, v2):
                        chunks = PolicyService(session).list_chunks(
                            seeded.policy_document_id,
                            seeded.policy_version_id,
                        )
                        for c in chunks:
                            hits.append(
                                RetrievalHit(
                                    chunk_id=c.id,
                                    policy_document_id=seeded.policy_document_id,
                                    policy_version_id=c.policy_version_id,
                                    chunk_index=c.chunk_index,
                                    content=c.content,
                                    section_id=c.section_id,
                                    section_title=c.section_title,
                                    page_number=c.page_number,
                                    source_filename=c.source_filename,
                                    content_hash=c.content_hash,
                                    embedding_model=c.embedding_model,
                                    distance=0.1,
                                    similarity=0.9,
                                )
                            )
                    return hits[:top_k]

            return settings, DualRetrieval(
                self._session, provider=self._provider, settings=settings
            )

        settings = Settings(
            policy_retrieval_min_similarity=0.01,
            policy_grounding_top_k=case.top_k,
            embedding_dimension=768,
        )
        return settings, PolicyRetrievalService(
            self._session, provider=self._provider, settings=settings
        )
