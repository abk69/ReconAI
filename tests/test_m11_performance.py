"""M11.5 performance, cost, and reliability evaluation."""

from decimal import Decimal

import pytest

from app.evaluation.m8_harness import make_eval_session
from app.evaluation.m11_performance_dataset import DATASET_ID, MEASURED_RUNS, WORKLOADS
from app.evaluation.m11_performance_harness import (
    classify_failure,
    evaluate_dataset,
    measure_provider,
    sample_cost,
)
from app.evaluation.m11_performance_stats import (
    COST_UNAVAILABLE,
    estimate_cost,
    monotonic_ms,
    percentile,
    summarize,
    usage_report,
)


def test_monotonic_clock_advances() -> None:
    start = monotonic_ms()
    end = monotonic_ms()
    assert end >= start


def test_percentile_nearest_rank_on_five_samples() -> None:
    values = [1.0, 2.0, 3.0, 4.0, 10.0]
    assert percentile(values, 95) == 10.0
    summary = summarize(values)
    assert summary["count"] == 5
    assert summary["min"] == 1.0
    assert summary["median"] == 3.0
    assert summary["p95"] == 10.0
    assert summary["max"] == 10.0
    assert summary["p95_method"] == "nearest-rank"


def test_fixed_repetition_is_configured() -> None:
    assert MEASURED_RUNS == 5
    report = evaluate_dataset(warmup_runs=0, measured_runs=2)
    assert report["latency"]["embedding"]["count"] == 2
    assert report["protocol"]["measured_runs"] == 2


def test_retry_timeout_and_failure_classes() -> None:
    success = measure_provider("success")
    retried = measure_provider("retry-then-success")
    timeout = measure_provider("timeout")
    malformed = measure_provider("malformed")
    unavailable = measure_provider("unavailable")
    limited = measure_provider("rate-limit")
    assert success["attempt_count"] == 1
    assert success["usage"]["status"] == "PROVIDER_REPORTED"
    assert success["usage"]["total_tokens"] == 18
    assert success["failure_class"] == "SUCCESS"
    assert retried["attempt_count"] == 2
    assert retried["retry_count"] == 1
    assert retried["within_retry_limit"] is True
    assert timeout["failure_class"] == "PROVIDER_TIMEOUT"
    assert timeout["attempt_count"] == 2
    assert malformed["failure_class"] == "PROVIDER_INVALID_RESPONSE"
    assert unavailable["failure_class"] == "PROVIDER_UNAVAILABLE"
    assert limited["failure_class"] == "PROVIDER_RATE_LIMIT"
    assert classify_failure("NETWORK") == "NETWORK_FAILURE"


def test_token_accounting_and_unavailable_usage() -> None:
    missing = usage_report(None, None, None)
    assert missing["status"] == "TOKEN_USAGE_UNAVAILABLE"
    reported = usage_report(11, 7, 18)
    assert reported["status"] == "PROVIDER_REPORTED"
    assert reported["input_tokens"] == 11
    with pytest.raises(ValueError):
        usage_report(-1, 1, 0)


def test_cost_fixture_and_unavailable_pricing() -> None:
    missing = estimate_cost(
        1000,
        500,
        input_price_per_million=None,
        output_price_per_million=None,
        pricing_version="m11.5-unpriced",
    )
    assert missing["status"] == COST_UNAVAILABLE
    priced = sample_cost(1_000_000, 1_000_000)
    assert priced["status"] == "ESTIMATED"
    assert priced["pricing_version"] == "test-fixture-not-billing"
    assert Decimal(priced["estimated_input_cost"]) == Decimal("2")
    assert Decimal(priced["estimated_output_cost"]) == Decimal("4")
    assert Decimal(priced["estimated_total_cost"]) == Decimal("6")


def test_offline_runner_reliability_gates() -> None:
    report = evaluate_dataset(warmup_runs=0, measured_runs=1)
    assert report["dataset"] == DATASET_ID
    assert report["mode"] == "OFFLINE_DETERMINISTIC_EVALUATION"
    assert report["m6_status"] == "NOT_RUN"
    assert report["cost"]["status"] == COST_UNAVAILABLE
    assert report["usage"]["extraction"]["status"] == "TOKEN_USAGE_UNAVAILABLE"
    assert report["regression_failures"] == []
    assert report["reliability"]["duplicate_side_effects"] == 0
    assert report["reliability"]["idempotency"]["same_result"] is True
    assert report["reliability"]["idempotency"]["different_key_blocked"] is True
    assert report["reliability"]["rollback"]["rolled_back"] is True
    assert report["reliability"]["invalid_plan_persisted"] is False
    assert report["reliability"]["contention"]["duplicate_side_effects"] == 0
    assert len(WORKLOADS) == 18


def test_repeated_report_non_timing_fields_match() -> None:
    first = evaluate_dataset(warmup_runs=0, measured_runs=1)
    second = evaluate_dataset(warmup_runs=0, measured_runs=1)
    assert first["dataset"] == second["dataset"]
    assert first["cost"] == second["cost"]
    assert first["regression_failures"] == second["regression_failures"]
    assert first["reliability"]["idempotency"]["request_count"] == 3
    assert first["reliability"]["idempotency"]["execution_count"] == 1


def test_eval_session_opens() -> None:
    session = make_eval_session()
    session.close()
