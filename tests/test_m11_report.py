"""M11.6 unified report contract. Offline only."""

import pytest

from app.evaluation.m11_report import (
    RECORDED_LIVE_M6,
    RECORDED_OFFLINE_LATENCY,
    build_report,
    render_markdown,
    report_json,
)


@pytest.fixture(scope="module")
def report() -> dict:
    return build_report()


def test_unified_report_is_deterministic_and_offline(report: dict) -> None:
    assert report_json(report) == report_json(build_report())
    assert report["calls_gemini"] is False
    assert report["mode"] == "OFFLINE_DETERMINISTIC_EVALUATION"
    assert "overall_score" not in report_json(report)
    assert report["evidence_complete"] is True


def test_extraction_and_rag_keep_source_denominators(report: dict) -> None:
    header = report["extraction"]["header_accuracy"]
    assert header == {"numerator": 58, "denominator": 58, "rate": "1.0000"}
    completeness = report["extraction"]["header_completeness"]
    assert completeness["numerator"] == 58
    assert completeness["denominator"] == 75
    assert report["extraction"]["m6_status"] == "NOT_RUN"
    assert report["extraction"]["line_completeness"]["denominator"] == 47
    hit = report["rag"]["retrieval"]["hit_at_1"]
    assert hit["defined_cases"] == 14
    assert hit["case_count"] == 15
    assert hit["value"] == "1.0000"
    assert report["rag"]["grounding"]["citation_recall"]["value"] == "0.6786"


def test_safety_security_and_recorded_performance(report: dict) -> None:
    assert report["agent_safety"]["metrics"]["blocked_safely"] == 30
    assert report["agent_safety"]["metrics"]["prompt_injection_cases"] == 3
    assert report["agent_safety"]["metrics"]["unexpectedly_executed"] == 0
    assert report["security"]["metrics"]["blocked_safely"] == 25
    assert report["security"]["metrics"]["secret_leakage_count"] == 0
    assert report["security"]["metrics"]["frontend"]["dangerously_set_inner_html"] == 0
    assert report["performance"]["cost_status"] == "COST_UNAVAILABLE"
    assert report["performance"]["recorded_offline_latency"] == RECORDED_OFFLINE_LATENCY
    assert RECORDED_OFFLINE_LATENCY["stages"]["m4"]["count"] == 40
    assert RECORDED_OFFLINE_LATENCY["stages"]["execution"]["count"] == 1
    assert RECORDED_LIVE_M6["cost"]["status"] == "COST_UNAVAILABLE"
    assert RECORDED_LIVE_M6["usage"]["total_tokens"] == 580
    assert all(item["m11_6_status"] == "NOT_RERUN" for item in report["live_smoke_tests"])


def test_markdown_has_required_sections_and_no_score(report: dict) -> None:
    text = render_markdown(report)
    for heading in (
        "# M11 Evaluation Evidence",
        "## Evaluation matrix",
        "## Extraction",
        "## RAG / grounding",
        "## Agent safety",
        "## Security / prompt injection",
        "## Performance, cost, and reliability",
        "## Regression gates",
        "## Live Gemini smoke tests",
        "## Limitations",
        "## Reproducibility",
    ):
        assert heading in text
    assert "overall score" not in text.lower()
    assert "production ready" in text.lower()
