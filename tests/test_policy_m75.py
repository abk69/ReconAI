"""M7.5 RAG evaluation metrics, corpus, and runner tests (offline)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_corpus import seed_eval_corpus
from app.evaluation.m7_golden import DATASET_ID, EVAL_CASES, get_case
from app.evaluation.m7_grounding_eval import PolicyGroundingEvaluator
from app.evaluation.m7_metrics import (
    answer_fact_accuracy,
    citation_precision,
    citation_recall,
    hit_at_k,
    mean_reciprocal_rank,
    recall_at_k,
)
from app.evaluation.m7_retrieval_eval import PolicyRetrievalEvaluator
from app.evaluation.m7_runner import run_offline_evaluation


def test_hit_at_k() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    assert hit_at_k([b, a, c], {a}, k=3) == 1.0
    assert hit_at_k([b, c], {a}, k=2) == 0.0
    assert hit_at_k([a], {a}, k=1) == 1.0
    assert hit_at_k([a, b], set(), k=2) is None


def test_recall_at_k() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    assert recall_at_k([a, c], {a, b}, k=2) == 0.5
    assert recall_at_k([a, b], {a, b}, k=2) == 1.0
    assert recall_at_k([c], {a, b}, k=1) == 0.0
    assert recall_at_k([a], set(), k=1) is None


def test_mrr() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    assert mean_reciprocal_rank([b, a, c], {a}) == 0.5
    assert mean_reciprocal_rank([a, b], {a}) == 1.0
    assert mean_reciprocal_rank([b, c], {a}) == 0.0
    assert mean_reciprocal_rank([a], set()) is None


def test_citation_precision_recall() -> None:
    a, b, c = uuid4(), uuid4(), uuid4()
    assert citation_precision({a, c}, {a, b}) == 0.5
    assert citation_precision(set(), {a}) is None
    assert citation_recall({a}, {a, b}) == 0.5
    assert citation_recall({a}, set()) is None


def test_answer_fact_accuracy() -> None:
    text = "allowed_variance_percent is 2 and requires review above 2"
    assert answer_fact_accuracy({"allowed_variance_percent": "2"}, text) == 1.0
    assert answer_fact_accuracy({"allowed_variance_percent": "3"}, text) == 0.0
    assert answer_fact_accuracy({}, text) is None


def test_retrieval_evaluator_deterministic(db_session: Session) -> None:
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(db_session, embedding_provider=provider)
    evaluator = PolicyRetrievalEvaluator(
        db_session, corpus=corpus, embedding_provider=provider
    )
    first = evaluator.evaluate()
    second = evaluator.evaluate()
    assert first["retrieval"] == second["retrieval"]
    assert first["case_results"] == second["case_results"]
    assert first["dataset"] == DATASET_ID
    # Relevant price case should hit.
    price = next(r for r in first["case_results"] if r["case_id"] == "ret-price-relevant")
    assert price["hit_at_k"] == 1.0
    assert price["recall_at_k"] is not None and price["recall_at_k"] > 0


def test_version_specific_retrieval(db_session: Session) -> None:
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(db_session, embedding_provider=provider)
    evaluator = PolicyRetrievalEvaluator(
        db_session, corpus=corpus, embedding_provider=provider
    )
    v1 = evaluator.evaluate_case(get_case("ret-version-2pct"))
    v2 = evaluator.evaluate_case(get_case("ret-version-3pct"))
    assert v1.hit_at_k == 1.0
    assert v2.hit_at_k == 1.0
    # Different version scopes → different expected chunk sets.
    assert set(v1.expected_chunk_ids) != set(v2.expected_chunk_ids)


def test_grounding_supported_and_facts(db_session: Session) -> None:
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(db_session, embedding_provider=provider)
    evaluator = PolicyGroundingEvaluator(
        db_session, corpus=corpus, embedding_provider=provider
    )
    result = evaluator.evaluate_case(get_case("ret-price-relevant"))
    assert result.status_match
    assert result.actual_status == "SUPPORTED"
    assert result.citation_precision == 1.0
    assert result.answer_fact_accuracy == 1.0
    assert result.gemini_calls == 1


def test_insufficient_no_gemini_call(db_session: Session) -> None:
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(db_session, embedding_provider=provider)
    evaluator = PolicyGroundingEvaluator(
        db_session, corpus=corpus, embedding_provider=provider
    )
    empty = evaluator.evaluate_case(get_case("gnd-empty-kb"))
    assert empty.actual_status == "INSUFFICIENT_EVIDENCE"
    assert empty.gemini_calls == 0
    weak = evaluator.evaluate_case(get_case("gnd-weak-threshold"))
    assert weak.actual_status == "INSUFFICIENT_EVIDENCE"
    assert weak.gemini_calls == 0


def test_fabricated_and_zero_citation(db_session: Session) -> None:
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(db_session, embedding_provider=provider)
    evaluator = PolicyGroundingEvaluator(
        db_session, corpus=corpus, embedding_provider=provider
    )
    fab = evaluator.evaluate_case(get_case("gnd-citation-fabricated"))
    assert fab.actual_status == "INSUFFICIENT_EVIDENCE"
    zero = evaluator.evaluate_case(get_case("gnd-zero-citation-supported"))
    assert zero.actual_status == "INSUFFICIENT_EVIDENCE"


def test_conflicting_versions(db_session: Session) -> None:
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(db_session, embedding_provider=provider)
    evaluator = PolicyGroundingEvaluator(
        db_session, corpus=corpus, embedding_provider=provider
    )
    result = evaluator.evaluate_case(get_case("gnd-conflict-active"))
    assert result.actual_status == "CONFLICTING_POLICY"
    assert result.gemini_calls == 0
    assert result.status_match


def test_evaluation_report_structure() -> None:
    report = run_offline_evaluation()
    assert report["dataset"] == DATASET_ID
    assert "retrieval" in report
    assert "grounding" in report
    assert "hit_at_3" in report["retrieval"]
    assert "recall_at_3" in report["retrieval"]
    assert "mrr" in report["retrieval"]
    assert "citation_precision" in report["grounding"]
    assert "citation_recall" in report["grounding"]
    assert "answer_fact_accuracy" in report["grounding"]
    assert "abstention_accuracy" in report["grounding"]
    # No single overall score key.
    assert "overall_score" not in report
    assert "rag_score" not in report


def test_cli_runner_main(capsys: pytest.CaptureFixture[str]) -> None:
    # argparse reads sys.argv — invoke run_offline via main with no --live
    import sys

    from app.evaluation.m7_runner import main

    old = sys.argv
    try:
        sys.argv = ["m7_runner"]
        main()
    finally:
        sys.argv = old
    out = capsys.readouterr().out
    assert DATASET_ID in out
    assert "hit_at_3" in out


@pytest.mark.live_rag_eval
def test_live_rag_eval_smoke() -> None:
    import os

    from app.core.config import get_settings
    from app.evaluation.m7_runner import run_live_smoke

    get_settings.cache_clear()
    if not (os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key):
        pytest.skip("GEMINI_API_KEY not configured")
    report = run_live_smoke()
    assert report.get("live") is True
    assert report["retrieval_hit_count"] >= 1
    assert report["grounding_status"] in {
        "SUPPORTED",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTING_POLICY",
        "PROVIDER_ERROR",
    }
    assert report["exception_status_unchanged"] is True


def test_golden_dataset_has_required_categories() -> None:
    cats = {c.category.value for c in EVAL_CASES}
    for required in (
        "RELEVANT_POLICY",
        "NO_RELEVANT_POLICY",
        "VERSIONED_POLICY",
        "CONFLICTING_POLICY",
        "CITATION_GROUNDING",
        "BOUNDARY_CASE",
    ):
        assert required in cats
