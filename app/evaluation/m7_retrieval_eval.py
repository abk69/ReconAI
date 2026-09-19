"""M7.5 policy retrieval evaluator (deterministic)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_corpus import EvalCorpus, resolve_expected_chunk_ids, seed_eval_corpus
from app.evaluation.m7_golden import DATASET_ID, EVAL_CASES, EvaluationCase
from app.evaluation.m7_metrics import hit_at_k, mean_defined, mean_reciprocal_rank, recall_at_k
from app.services.policy_retrieval_service import PolicyRetrievalService

# Cases that are grounding-simulation only (not ranked retrieval).
_SKIP_RETRIEVAL_MODES = frozenset(
    {
        "conflict",
        "insufficient_empty_kb",
        "insufficient_high_threshold",
        "fabricated_citation",
        "zero_citation_supported",
    }
)


@dataclass
class RetrievalCaseResult:
    case_id: str
    category: str
    query: str
    top_k: int
    expected_chunk_ids: list[str]
    retrieved_chunk_ids: list[str]
    hit_at_k: float | None
    recall_at_k: float | None
    mrr: float | None
    notes: str = ""


class PolicyRetrievalEvaluator:
    """Run golden retrieval cases against a seeded corpus + FakeEmbeddingProvider."""

    def __init__(
        self,
        session: Session,
        *,
        corpus: EvalCorpus | None = None,
        embedding_provider: FakeEmbeddingProvider | None = None,
        settings: Settings | None = None,
        k: int = 3,
    ) -> None:
        self._session = session
        self._provider = embedding_provider or FakeEmbeddingProvider(
            model="fake-embedding-eval",
            dimension=768,
        )
        self._settings = settings or Settings(
            policy_retrieval_min_similarity=0.0,
            embedding_dimension=768,
        )
        self._corpus = corpus or seed_eval_corpus(session, embedding_provider=self._provider)
        self._retrieval = PolicyRetrievalService(
            session,
            provider=self._provider,
            settings=self._settings,
        )
        self._k = k

    @property
    def corpus(self) -> EvalCorpus:
        return self._corpus

    def evaluate_case(self, case: EvaluationCase) -> RetrievalCaseResult:
        k = case.top_k or self._k
        expected = resolve_expected_chunk_ids(
            self._corpus,
            policy_key=case.policy_key,
            section_ids=case.expected_section_ids,
            content_markers=case.expected_content_markers,
            session=self._session,
        )
        version_id: UUID | None = None
        if case.policy_key and case.policy_key in self._corpus.policies:
            version_id = self._corpus.policies[case.policy_key].policy_version_id

        hits = self._retrieval.retrieve_policy_chunks(
            case.query,
            top_k=k,
            policy_version_id=version_id,
        )
        retrieved_ids = [h.chunk_id for h in hits]

        return RetrievalCaseResult(
            case_id=case.id,
            category=case.category.value,
            query=case.query,
            top_k=k,
            expected_chunk_ids=[str(i) for i in sorted(expected, key=str)],
            retrieved_chunk_ids=[str(i) for i in retrieved_ids],
            hit_at_k=hit_at_k(retrieved_ids, expected, k=k),
            recall_at_k=recall_at_k(retrieved_ids, expected, k=k),
            mrr=mean_reciprocal_rank(retrieved_ids, expected),
            notes=case.notes,
        )

    def evaluate(
        self,
        cases: list[EvaluationCase] | None = None,
    ) -> dict[str, Any]:
        pool = cases or EVAL_CASES
        retrieval_cases = [
            c for c in pool if (c.grounding_mode or "") not in _SKIP_RETRIEVAL_MODES
        ]
        results = [self.evaluate_case(c) for c in retrieval_cases]
        return {
            "dataset": DATASET_ID,
            "cases": len(results),
            "retrieval": {
                "hit_at_3": mean_defined([r.hit_at_k for r in results]),
                "recall_at_3": mean_defined([r.recall_at_k for r in results]),
                "mrr": mean_defined([r.mrr for r in results]),
            },
            "case_results": [asdict(r) for r in results],
        }
