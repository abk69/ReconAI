"""Offline RAG and grounding scoring for m11_rag_eval_v1.

Retrieval and citation math come from M7.5. This module does not change
production retrieval or prompts.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import PolicyChunk, ReconciliationException
from app.domain.enums import ExceptionSeverity, ExceptionStatus, ExceptionType
from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_corpus import EvalCorpus, seed_eval_corpus
from app.evaluation.m7_grounding_eval import _parse_allowlist
from app.evaluation.m7_metrics import (
    answer_fact_accuracy,
    citation_precision,
    citation_recall,
    hit_at_k,
    mean_defined,
    mean_reciprocal_rank,
    recall_at_k,
)
from app.evaluation.m11_rag_dataset import (
    CASES,
    DATASET_ID,
    INJECTION_TEXT,
    POLICIES,
    RagEvalCase,
)
from app.llm.base import LLMUsageMetadata, StructuredLLMResponse
from app.llm.grounding_prompts import SYSTEM_INSTRUCTION
from app.llm.grounding_schemas import GroundedPolicyGeminiOutput
from app.services.policy_grounding_service import PolicyGroundingService
from app.services.policy_retrieval_service import PolicyRetrievalService, RetrievalHit
from app.services.policy_service import PolicyService

K_VALUES = (1, 3, 5)
RETRIEVAL_TOP_K = 5

# Engineering floors for this dataset. Not production accuracy targets.
REGRESSION_GATES: dict[str, str] = {
    "hit_at_1": "1.0000",
    "hit_at_3": "1.0000",
    "hit_at_5": "1.0000",
    "recall_at_1": "0.8929",
    "recall_at_3": "1.0000",
    "recall_at_5": "1.0000",
    "mrr": "1.0000",
    "answer_fact_accuracy": "1.0000",
    "citation_precision": "1.0000",
    "citation_recall": "0.6786",
    "abstention_accuracy": "1.0000",
}


def _rate(value: float | None) -> str | None:
    if value is None:
        return None
    return str(Decimal(str(value)).quantize(Decimal("0.0001")))


def _defined_summary(values: list[float | None]) -> dict[str, Any]:
    defined = [item for item in values if item is not None]
    return {
        "value": _rate(mean_defined(values)),
        "numerator_sum": _rate(sum(defined) if defined else None),
        "defined_cases": len(defined),
        "case_count": len(values),
    }


class _ScriptedGroundingLLM:
    """Deterministic stand-in. Policy text is never copied into the system role."""

    def __init__(
        self,
        mode: str,
        *,
        facts: dict[str, str],
        expected: set[UUID],
    ) -> None:
        self.mode = mode
        self.facts = facts
        self.expected = expected
        self.calls = 0
        self.model = "fake-grounding-eval"
        self.system_instruction_unchanged = True
        self.injection_in_system = False
        self.injection_in_user = False
        self.followed_injection = False

    def generate_structured(self, *, system_instruction, user_content, response_model):
        self.calls += 1
        self.system_instruction_unchanged = system_instruction == SYSTEM_INSTRUCTION
        self.injection_in_system = INJECTION_TEXT in (system_instruction or "")
        self.injection_in_user = INJECTION_TEXT in (user_content or "")
        allow = _parse_allowlist(user_content)
        if self.injection_in_system:
            self.followed_injection = True
            conclusion = "UNSAFE_FOLLOWED_POLICY_INSTRUCTION"
            cites: list[str] = []
            status = "SUPPORTED"
        else:
            conclusion, cites, status = self._output(allow)
        fact_text = " ".join(self.facts.values())
        if status == "SUPPORTED" and not self.followed_injection:
            conclusion = f"{conclusion} {fact_text}".strip()
        output = GroundedPolicyGeminiOutput(
            status=status,  # type: ignore[arg-type]
            conclusion=conclusion,
            explanation=(
                fact_text if status == "SUPPORTED" else "Evidence does not support an answer."
            ),
            policy_support=fact_text if status == "SUPPORTED" else "",
            cited_chunk_ids=cites,
            limitations="",
        )
        return StructuredLLMResponse(
            output=output,
            raw_text=None,
            model=self.model,
            provider="fake",
            usage=LLMUsageMetadata(),
        )

    def _output(self, allow: list[str]) -> tuple[str, list[str], str]:
        expected = [item for item in allow if UUID(item) in self.expected]
        other = [item for item in allow if item not in expected]
        if self.mode == "unknown_citation":
            return "Unknown cite.", [str(uuid4())], "SUPPORTED"
        if self.mode == "missing_citation":
            return "Missing cite.", [], "SUPPORTED"
        if self.mode == "wrong_citation":
            cited = other[:1] or [str(uuid4())]
            return "Wrong cite.", cited, "SUPPORTED"
        if self.mode == "extra_citation":
            cited = (expected[:1] or allow[:1]) + other[:1]
            return "Extra cite.", cited, "SUPPORTED"
        if self.mode == "model_abstain":
            return (
                "The evidence does not support the requested conclusion.",
                [],
                "INSUFFICIENT_EVIDENCE",
            )
        if self.mode == "retrieved_or_abstain":
            return "No relevant policy evidence.", [], "INSUFFICIENT_EVIDENCE"
        cited = expected or allow[:1]
        return "Policy evidence supports the recorded fact.", cited, "SUPPORTED"

    def extract_structured(self, *, system_instruction, user_content):
        raise NotImplementedError


def expected_chunk_ids(corpus: EvalCorpus, case: RagEvalCase, session: Session) -> set[UUID]:
    """Relevant chunk = seeded chunk on a case policy whose section or markers match.

    Same rule as M7.5 ``resolve_expected_chunk_ids``: section ids and content
    markers are unioned. An empty expectation means the metric is undefined.
    """
    if not case.expected_section_ids and not case.expected_content_markers:
        return set()
    keys = case.policy_keys or tuple(corpus.policies.keys())
    found: set[UUID] = set()
    for key in keys:
        seeded = corpus.policies.get(key)
        if seeded is None:
            continue
        for section_id in case.expected_section_ids:
            found.update(seeded.chunks_by_section.get(section_id, []))
        if case.expected_content_markers:
            for chunk_id in seeded.all_chunk_ids:
                chunk = session.get(PolicyChunk, chunk_id)
                if chunk is None:
                    continue
                text = chunk.content.casefold()
                if all(marker.casefold() in text for marker in case.expected_content_markers):
                    found.add(chunk_id)
    return found


def _version_id(corpus: EvalCorpus, case: RagEvalCase) -> UUID | None:
    if not case.scope_version or len(case.policy_keys) != 1:
        return None
    seeded = corpus.policies.get(case.policy_keys[0])
    if seeded is None:
        return None
    return seeded.policy_version_id


class _ConflictRetrieval(PolicyRetrievalService):
    """Return both ACTIVE price versions. Production retrieval is unchanged."""

    def __init__(self, session: Session, corpus: EvalCorpus, settings: Settings, provider) -> None:
        super().__init__(session, provider=provider, settings=settings)
        self._corpus = corpus

    def retrieve_policy_chunks(
        self,
        query,
        *,
        top_k=5,
        policy_document_id=None,
        policy_version_id=None,
    ):
        hits: list[RetrievalHit] = []
        for key in ("price_m11_a", "price_m11_b"):
            seeded = self._corpus.policies[key]
            chunks = PolicyService(self._session).list_chunks(
                seeded.policy_document_id,
                seeded.policy_version_id,
            )
            for chunk in chunks:
                if chunk.section_id != "2":
                    continue
                hits.append(
                    RetrievalHit(
                        chunk_id=chunk.id,
                        policy_document_id=seeded.policy_document_id,
                        policy_version_id=chunk.policy_version_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        section_id=chunk.section_id,
                        section_title=chunk.section_title,
                        page_number=chunk.page_number,
                        source_filename=chunk.source_filename,
                        content_hash=chunk.content_hash,
                        embedding_model=chunk.embedding_model,
                        distance=0.1,
                        similarity=0.9,
                    )
                )
        return hits[:top_k]


def _retrieval_service(
    session: Session,
    corpus: EvalCorpus,
    provider: FakeEmbeddingProvider,
    case: RagEvalCase,
) -> tuple[Settings, PolicyRetrievalService]:
    if case.grounding_mode in {"wrong_citation", "extra_citation"}:
        settings = Settings(
            policy_retrieval_min_similarity=0.20,
            policy_grounding_top_k=RETRIEVAL_TOP_K,
            embedding_dimension=768,
        )
    elif case.grounding_mode == "below_threshold":
        settings = Settings(
            policy_retrieval_min_similarity=0.999,
            policy_grounding_top_k=RETRIEVAL_TOP_K,
            embedding_dimension=768,
        )
    elif case.grounding_mode == "conflict":
        settings = Settings(
            policy_retrieval_min_similarity=0.25,
            policy_grounding_top_k=RETRIEVAL_TOP_K,
            embedding_dimension=768,
        )
        return settings, _ConflictRetrieval(session, corpus, settings, provider)
    else:
        settings = Settings(
            policy_retrieval_min_similarity=0.25,
            policy_grounding_top_k=RETRIEVAL_TOP_K,
            embedding_dimension=768,
        )
    return settings, PolicyRetrievalService(session, provider=provider, settings=settings)


def score_retrieval(
    session: Session,
    corpus: EvalCorpus,
    provider: FakeEmbeddingProvider,
    case: RagEvalCase,
) -> dict[str, Any]:
    settings = Settings(
        policy_retrieval_min_similarity=0.0,
        embedding_dimension=768,
    )
    service = PolicyRetrievalService(session, provider=provider, settings=settings)
    expected = expected_chunk_ids(corpus, case, session)
    hits = service.retrieve_policy_chunks(
        case.query,
        top_k=RETRIEVAL_TOP_K,
        policy_version_id=_version_id(corpus, case),
    )
    retrieved = [hit.chunk_id for hit in hits]
    row: dict[str, Any] = {
        "expected_count": len(expected),
        "retrieved_count": len(retrieved),
        "mrr": _rate(mean_reciprocal_rank(retrieved, expected)),
    }
    for k in K_VALUES:
        row[f"hit_at_{k}"] = _rate(hit_at_k(retrieved, expected, k=k))
        row[f"recall_at_{k}"] = _rate(recall_at_k(retrieved, expected, k=k))
    return row


def _errors(
    *,
    case: RagEvalCase,
    actual_status: str,
    cited: set[UUID],
    retrieved: set[UUID],
    expected: set[UUID],
    fact_accuracy: float | None,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if case.expected_status != actual_status:
        errors.append(
            {
                "case_id": case.case_id,
                "category": "STATUS_MISMATCH",
                "expected": case.expected_status,
                "actual": actual_status,
            }
        )
    if case.abstention_required and actual_status == "SUPPORTED":
        errors.append(
            {
                "case_id": case.case_id,
                "category": "INCORRECT_ANSWER",
                "expected": case.expected_status,
                "actual": actual_status,
            }
        )
    if (
        case.expected_facts
        and actual_status == "SUPPORTED"
        and fact_accuracy is not None
        and fact_accuracy < 1
    ):
        errors.append(
            {
                "case_id": case.case_id,
                "category": "UNSUPPORTED_ANSWER",
                "expected": json.dumps(case.expected_facts, sort_keys=True),
                "actual": str(fact_accuracy),
            }
        )
    unknown = cited - retrieved
    if case.grounding_mode == "unknown_citation" or unknown:
        errors.append(
            {
                "case_id": case.case_id,
                "category": "UNKNOWN_CITATION",
                "expected": "allowlisted chunk",
                "actual": "rejected" if not cited else "present",
            }
        )
    if case.grounding_mode == "missing_citation" and not cited:
        errors.append(
            {
                "case_id": case.case_id,
                "category": "MISSING_CITATION",
                "expected": "at least one citation",
                "actual": "none",
            }
        )
    if cited and expected and not (cited & expected) and not unknown:
        errors.append(
            {
                "case_id": case.case_id,
                "category": "WRONG_CITATION",
                "expected": "expected relevant chunk",
                "actual": "different retrieved chunk",
            }
        )
    extra = cited - expected
    if cited & expected and extra and not unknown:
        errors.append(
            {
                "case_id": case.case_id,
                "category": "EXTRA_CITATION",
                "expected": "expected relevant chunks",
                "actual": "additional citation",
            }
        )
    return errors


def score_grounding(
    session: Session,
    corpus: EvalCorpus,
    provider: FakeEmbeddingProvider,
    case: RagEvalCase,
) -> dict[str, Any]:
    expected = expected_chunk_ids(corpus, case, session)
    exc = ReconciliationException(
        exception_type=ExceptionType.OTHER.value,
        severity=ExceptionSeverity.MEDIUM.value,
        message=case.query,
        status=ExceptionStatus.OPEN.value,
        evidence={},
        fingerprint=f"m11-rag-{uuid4().hex}",
        source_document_ids=[],
    )
    session.add(exc)
    session.commit()
    llm = _ScriptedGroundingLLM(case.grounding_mode, facts=case.expected_facts, expected=expected)
    settings, retrieval = _retrieval_service(session, corpus, provider, case)
    result = PolicyGroundingService(
        session,
        llm=llm,  # type: ignore[arg-type]
        retrieval=retrieval,
        settings=settings,
    ).explain_exception(exc.id, policy_version_id=_version_id(corpus, case), persist=False)
    session.refresh(exc)
    cited = {item.chunk_id for item in result.citations}
    retrieved = set(result.retrieved_chunk_ids)
    text = " ".join([result.conclusion, result.explanation, result.policy_support])
    facts = answer_fact_accuracy(case.expected_facts, text)
    if result.status.value != "SUPPORTED":
        facts = None
    precision = citation_precision(cited, retrieved)
    recall = citation_recall(cited, expected)
    unsafe = (
        (not llm.system_instruction_unchanged)
        or llm.followed_injection
        or "UNSAFE_FOLLOWED_POLICY_INSTRUCTION" in text
        or exc.status != ExceptionStatus.OPEN.value
    )
    injection_case = case.grounding_mode == "injection_data"
    if injection_case and llm.calls and not llm.injection_in_user:
        unsafe = True
    errors = _errors(
        case=case,
        actual_status=result.status.value,
        cited=cited,
        retrieved=retrieved,
        expected=expected,
        fact_accuracy=facts,
    )
    return {
        "case_id": case.case_id,
        "expected_status": case.expected_status,
        "actual_status": result.status.value,
        "status_match": result.status.value == case.expected_status,
        "abstention_required": case.abstention_required,
        "answer_fact_accuracy": _rate(facts),
        "citation_precision": _rate(precision),
        "citation_recall": _rate(recall),
        "citation_count": len(cited),
        "gemini_calls": llm.calls,
        "conflict_detected": result.status.value == "CONFLICTING_POLICY",
        "injection_case": injection_case,
        "unsafe": unsafe,
        "exception_status": exc.status,
        "errors": errors,
    }


def evaluate_dataset(session: Session) -> dict[str, Any]:
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(session, embedding_provider=provider, policies=list(POLICIES))
    cases: list[dict[str, Any]] = []
    for case in CASES:
        retrieval = score_retrieval(session, corpus, provider, case)
        grounding = score_grounding(session, corpus, provider, case)
        cases.append(
            {
                "case_id": case.case_id,
                "expected_status": case.expected_status,
                "actual_status": grounding["actual_status"],
                "abstention_required": grounding["abstention_required"],
                "retrieval": retrieval,
                "facts": case.expected_facts,
                "answer_fact_accuracy": grounding["answer_fact_accuracy"],
                "citation_precision": grounding["citation_precision"],
                "citation_recall": grounding["citation_recall"],
                "citation_count": grounding["citation_count"],
                "gemini_calls": grounding["gemini_calls"],
                "conflict_detected": grounding["conflict_detected"],
                "injection_case": grounding["injection_case"],
                "unsafe": grounding["unsafe"],
                "errors": grounding["errors"],
            }
        )
    return _report(cases)


def _decimal_values(rows: list[dict[str, Any]], key: str) -> list[float | None]:
    values: list[float | None] = []
    for row in rows:
        raw = row["retrieval"][key] if key in row["retrieval"] else row.get(key)
        values.append(None if raw is None else float(raw))
    return values


def _report(cases: list[dict[str, Any]]) -> dict[str, Any]:
    retrieval: dict[str, Any] = {}
    for key in (
        "hit_at_1",
        "hit_at_3",
        "hit_at_5",
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "mrr",
    ):
        retrieval[key] = _defined_summary(_decimal_values(cases, key))
    fact_rows = [row for row in cases if row["answer_fact_accuracy"] is not None]
    prec_rows = [row for row in cases if row["citation_precision"] is not None]
    recall_rows = [row for row in cases if row["citation_recall"] is not None]
    abstain = [row for row in cases if row["abstention_required"]]
    abstain_correct = sum(1 for row in abstain if row["actual_status"] == row["expected_status"])
    conflict_cases = [row for row in cases if row["expected_status"] == "CONFLICTING_POLICY"]
    conflict_correct = sum(1 for row in conflict_cases if row["conflict_detected"])
    injection_cases = [row for row in cases if row["injection_case"]]
    unsafe = sum(1 for row in cases if row["unsafe"])
    violations = sum(1 for row in injection_cases if row["unsafe"])
    incorrect = sum(
        1
        for row in cases
        if any(error["category"] == "INCORRECT_ANSWER" for error in row["errors"])
    )
    unsupported = sum(
        1
        for row in cases
        if any(error["category"] == "UNSUPPORTED_ANSWER" for error in row["errors"])
    )
    grounding = {
        "answer_fact_accuracy": _defined_summary(
            [float(row["answer_fact_accuracy"]) for row in fact_rows]
        ),
        "citation_precision": _defined_summary(
            [float(row["citation_precision"]) for row in prec_rows]
        ),
        "citation_recall": _defined_summary(
            [float(row["citation_recall"]) for row in recall_rows]
        ),
        "abstention_accuracy": {
            "value": _rate(abstain_correct / len(abstain) if abstain else None),
            "correct": abstain_correct,
            "denominator": len(abstain),
        },
        "conflict_detection": {
            "value": _rate(conflict_correct / len(conflict_cases) if conflict_cases else None),
            "correct": conflict_correct,
            "denominator": len(conflict_cases),
        },
        "incorrect_answer_count": incorrect,
        "unsupported_answer_count": unsupported,
    }
    summary_values = {
        "hit_at_1": retrieval["hit_at_1"]["value"],
        "hit_at_3": retrieval["hit_at_3"]["value"],
        "hit_at_5": retrieval["hit_at_5"]["value"],
        "recall_at_1": retrieval["recall_at_1"]["value"],
        "recall_at_3": retrieval["recall_at_3"]["value"],
        "recall_at_5": retrieval["recall_at_5"]["value"],
        "mrr": retrieval["mrr"]["value"],
        "answer_fact_accuracy": grounding["answer_fact_accuracy"]["value"],
        "citation_precision": grounding["citation_precision"]["value"],
        "citation_recall": grounding["citation_recall"]["value"],
        "abstention_accuracy": grounding["abstention_accuracy"]["value"],
    }
    failures = []
    for metric, floor in REGRESSION_GATES.items():
        actual = summary_values[metric]
        if actual is None:
            continue
        if Decimal(actual) < Decimal(floor):
            failures.append(f"{metric} {actual} < {floor}")
    return {
        "dataset": DATASET_ID,
        "mode": "OFFLINE_DETERMINISTIC_EVALUATION",
        "documents": len(POLICIES),
        "cases_evaluated": len(cases),
        "retrieval": retrieval,
        "grounding": grounding,
        "security": {
            "prompt_injection_cases": len(injection_cases),
            "unsafe_behavior_count": unsafe,
            "instruction_following_violations": violations,
            "injection_treated_as_data": all(
                not row["unsafe"] for row in injection_cases
            ),
        },
        "regression_failures": failures,
        "cases": cases,
        "note": (
            "Synthetic offline results use FakeEmbeddingProvider and a scripted model. "
            "They are not production accuracy."
        ),
    }


def regression_failures(report: dict[str, Any]) -> list[str]:
    return list(report["regression_failures"])
