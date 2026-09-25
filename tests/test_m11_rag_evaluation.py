"""M11.2 RAG and grounding evaluation tests. Offline only."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_corpus import seed_eval_corpus
from app.evaluation.m7_metrics import hit_at_k, mean_reciprocal_rank, recall_at_k
from app.evaluation.m11_rag_dataset import CASES, DATASET_ID, POLICIES, case_by_id
from app.evaluation.m11_rag_harness import evaluate_dataset, score_grounding
from app.evaluation.m11_rag_runner import run_live, run_offline


def _case(report: dict, case_id: str) -> dict:
    return next(row for row in report["cases"] if row["case_id"] == case_id)


def test_dataset_covers_required_cases() -> None:
    assert DATASET_ID == "m11_rag_eval_v1"
    assert len(CASES) == 15
    assert len(POLICIES) == 5
    ids = {case.case_id for case in CASES}
    assert {
        "direct-support",
        "paraphrased-support",
        "multi-chunk",
        "irrelevant-corpus",
        "insufficient-evidence",
        "conflicting-versions",
        "citation-required",
        "citation-mismatch",
        "low-similarity",
        "version-boundary",
        "multiple-documents",
        "injection-policy-text",
        "injection-retrieved-chunk",
        "unsupported-conclusion",
        "below-threshold",
    } == ids


def test_retrieval_metrics_and_denominators() -> None:
    report = run_offline()
    retrieval = report["retrieval"]
    assert retrieval["hit_at_1"]["defined_cases"] == 14
    assert retrieval["hit_at_1"]["case_count"] == 15
    assert retrieval["hit_at_1"]["value"] == "1.0000"
    assert retrieval["hit_at_3"]["value"] == "1.0000"
    assert retrieval["hit_at_5"]["value"] == "1.0000"
    assert retrieval["recall_at_1"]["value"] == "0.8929"
    assert retrieval["recall_at_5"]["value"] == "1.0000"
    assert retrieval["mrr"]["defined_cases"] == 14
    direct = _case(report, "direct-support")
    assert direct["retrieval"]["hit_at_1"] == "1.0000"
    irrelevant = _case(report, "irrelevant-corpus")
    assert irrelevant["retrieval"]["hit_at_1"] is None
    assert irrelevant["retrieval"]["expected_count"] == 0
    assert irrelevant["actual_status"] == "INSUFFICIENT_EVIDENCE"


def test_metric_definitions_match_m7() -> None:
    from uuid import uuid4

    relevant, other = uuid4(), uuid4()
    assert hit_at_k([other, relevant], {relevant}, k=1) == 0.0
    assert hit_at_k([other, relevant], {relevant}, k=3) == 1.0
    assert recall_at_k([relevant], {relevant, other}, k=1) == 0.5
    assert mean_reciprocal_rank([other, relevant], {relevant}) == 0.5
    assert hit_at_k([relevant], set(), k=1) is None


def test_grounding_facts_citations_and_abstention() -> None:
    report = run_offline()
    grounding = report["grounding"]
    assert grounding["answer_fact_accuracy"]["value"] == "1.0000"
    assert grounding["answer_fact_accuracy"]["defined_cases"] == 10
    assert grounding["citation_precision"]["value"] == "1.0000"
    assert grounding["citation_precision"]["defined_cases"] == 11
    assert grounding["citation_recall"]["defined_cases"] == 14
    assert grounding["abstention_accuracy"] == {
        "value": "1.0000",
        "correct": 5,
        "denominator": 5,
    }
    assert grounding["conflict_detection"]["correct"] == 1
    assert grounding["incorrect_answer_count"] == 0
    mismatch = _case(report, "citation-mismatch")
    assert mismatch["actual_status"] == "SUPPORTED"
    assert mismatch["errors"][0]["category"] == "WRONG_CITATION"
    assert _case(report, "insufficient-evidence")["gemini_calls"] == 0
    assert _case(report, "below-threshold")["actual_status"] == "INSUFFICIENT_EVIDENCE"
    assert _case(report, "unsupported-conclusion")["actual_status"] == "INSUFFICIENT_EVIDENCE"
    assert _case(report, "conflicting-versions")["actual_status"] == "CONFLICTING_POLICY"


def test_prompt_injection_stays_data() -> None:
    report = run_offline()
    security = report["security"]
    assert security["prompt_injection_cases"] == 2
    assert security["unsafe_behavior_count"] == 0
    assert security["instruction_following_violations"] == 0
    assert security["injection_treated_as_data"] is True
    for case_id in ("injection-policy-text", "injection-retrieved-chunk"):
        row = _case(report, case_id)
        assert row["actual_status"] == "SUPPORTED"
        assert row["unsafe"] is False
        assert row["citation_count"] >= 1


def test_citation_allowlist_modes() -> None:
    from app.evaluation.m11_rag_runner import make_session

    session = make_session()
    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    corpus = seed_eval_corpus(session, embedding_provider=provider, policies=list(POLICIES))
    base = case_by_id("citation-required")
    missing = score_grounding(
        session, corpus, provider, replace(base, grounding_mode="missing_citation")
    )
    unknown = score_grounding(
        session, corpus, provider, replace(base, grounding_mode="unknown_citation")
    )
    extra = score_grounding(
        session,
        corpus,
        provider,
        replace(case_by_id("citation-mismatch"), grounding_mode="extra_citation"),
    )
    session.close()
    assert missing["actual_status"] == "INSUFFICIENT_EVIDENCE"
    assert missing["citation_count"] == 0
    assert any(error["category"] == "MISSING_CITATION" for error in missing["errors"])
    assert unknown["actual_status"] == "INSUFFICIENT_EVIDENCE"
    assert unknown["citation_count"] == 0
    assert any(error["category"] == "UNKNOWN_CITATION" for error in unknown["errors"])
    assert extra["actual_status"] == "SUPPORTED"
    assert any(error["category"] == "EXTRA_CITATION" for error in extra["errors"])
    assert extra["citation_precision"] == "1.0000"


def test_offline_runner_is_deterministic() -> None:
    first = run_offline()
    second = run_offline()
    assert first == second
    assert first["dataset"] == DATASET_ID
    assert first["mode"] == "OFFLINE_DETERMINISTIC_EVALUATION"
    assert first["regression_failures"] == []


def test_live_mode_unavailable_without_key() -> None:
    result = run_live(api_key="")
    assert result["status"] == "LIVE_NOT_RUN"
    assert result["dataset"] == DATASET_ID


def test_evaluate_dataset_matches_runner(db_session) -> None:
    report = evaluate_dataset(db_session)
    assert report["cases_evaluated"] == 15
    assert report["regression_failures"] == []


@pytest.mark.live_rag_eval
def test_live_rag_eval_smoke() -> None:
    result = run_live()
    if result["status"] == "LIVE_NOT_RUN":
        pytest.skip("GEMINI_API_KEY is not configured")
    assert result["status"] == "OK"
