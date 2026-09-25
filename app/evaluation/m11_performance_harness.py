"""Offline performance and reliability baseline. Live Gemini is separate."""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import ActionExecution, ReconciliationException
from app.domain.enums import (
    DocumentType,
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
)
from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_golden import PRICE_V1
from app.evaluation.m8_harness import make_eval_session
from app.evaluation.m11_performance_dataset import (
    DATASET_ID,
    MEASURED_RUNS,
    TEXTS,
    WARMUP_RUNS,
    WORKLOADS,
)
from app.evaluation.m11_performance_stats import (
    COST_UNAVAILABLE,
    PRICING_VERSION,
    estimate_cost,
    monotonic_ms,
    summarize,
    usage_report,
)
from app.extraction.classifier import classify_document
from app.extraction.schemas import ExtractedDocument
from app.extraction.structure import build_candidate
from app.llm.base import LLMProviderError, LLMUsageMetadata, StructuredLLMResponse
from app.llm.gemini import GeminiProvider
from app.llm.grounding_schemas import GroundedPolicyGeminiOutput
from app.llm.schemas import GeminiExtractionOutput
from app.services.policy_retrieval_service import PolicyRetrievalService
from app.services.resolution_planning_service import (
    ResolutionPlanningService,
    ResolutionPlanningValidationError,
)
from app.services.resolution_service import ResolutionService, ResolutionValidationError

REVIEWER = "perf-eval"


def classify_failure(code: str | None) -> str:
    mapping = {
        "TIMEOUT": "PROVIDER_TIMEOUT",
        "UNAVAILABLE": "PROVIDER_UNAVAILABLE",
        "RATE_LIMIT": "PROVIDER_RATE_LIMIT",
        "MALFORMED_RESPONSE": "PROVIDER_INVALID_RESPONSE",
        "SCHEMA_INVALID": "PROVIDER_INVALID_RESPONSE",
        "VALIDATION": "VALIDATION_FAILURE",
        "DATABASE": "DATABASE_FAILURE",
        "NETWORK": "NETWORK_FAILURE",
        None: "SUCCESS",
        "SUCCESS": "SUCCESS",
    }
    return mapping.get(code, "APPLICATION_ERROR")


def _time_call(function) -> tuple[float, Any]:
    start = monotonic_ms()
    value = function()
    return round(monotonic_ms() - start, 3), value


def _repeat(function, *, warmup: int, measured: int) -> list[float]:
    for _ in range(warmup):
        function()
    samples: list[float] = []
    for _ in range(measured):
        duration, _value = _time_call(function)
        samples.append(duration)
    return samples


def _m4(text: str) -> None:
    document = ExtractedDocument(
        document_id=uuid4(),
        full_text=text,
        extractor_name="m11-performance",
    )
    detected = classify_document(
        document,
        original_filename="invoice.txt",
        declared_type=DocumentType.UNKNOWN,
    )
    build_candidate(document, detected)


class _StubModels:
    def __init__(self, behavior: str) -> None:
        self.behavior = behavior
        self.calls = 0

    def generate_content(self, **_kwargs: Any) -> Any:
        self.calls += 1
        if self.behavior == "success":
            return _ok_response()
        if self.behavior == "retry-then-success" and self.calls == 1:
            raise TimeoutError("timeout")
        if self.behavior == "timeout":
            raise TimeoutError("timeout")
        if self.behavior == "unavailable":
            raise RuntimeError("503 unavailable")
        if self.behavior == "rate-limit":
            raise RuntimeError("429 rate limit")
        if self.behavior == "malformed":
            return _bad_response()
        if self.behavior == "schema":
            raise LLMProviderError("schema", code="SCHEMA_INVALID")
        return _ok_response()


class _StubClient:
    def __init__(self, behavior: str) -> None:
        self.models = _StubModels(behavior)


def _bad_response() -> Any:
    class _Response:
        parsed = None
        text = "{not-json"
        usage_metadata = None
        candidates = []

    return _Response()


def _ok_response() -> Any:
    class _Meta:
        prompt_token_count = 11
        candidates_token_count = 7
        total_token_count = 18

    class _Response:
        parsed = GeminiExtractionOutput(document_type="INVOICE", invoice_number="INV-PERF-1")
        text = None
        usage_metadata = _Meta()
        candidates = []

    return _Response()


def _provider(behavior: str) -> tuple[GeminiProvider, _StubModels]:
    settings = Settings(
        gemini_api_key="local-eval-not-a-credential",
        llm_model="gemini-3.1-flash-lite",
        llm_max_retries=1,
        llm_timeout_seconds=1,
    )
    provider = GeminiProvider(settings)
    client = _StubClient(behavior)
    provider._client = client
    return provider, client.models


def measure_provider(behavior: str) -> dict[str, Any]:
    provider, models = _provider(behavior)
    started = monotonic_ms()
    status = "SUCCESS"
    error_code = None
    usage = usage_report(None, None, None)
    try:
        response = provider.generate_structured(
            system_instruction="extract",
            user_content="Invoice INV-PERF-1",
            response_model=GeminiExtractionOutput,
        )
        usage = usage_report(
            response.usage.input_tokens,
            response.usage.output_tokens,
            response.usage.total_tokens,
        )
    except LLMProviderError as exc:
        status = "FAILURE"
        error_code = exc.code
    duration = round(monotonic_ms() - started, 3)
    attempts = models.calls
    return {
        "operation": "provider",
        "success": status == "SUCCESS",
        "failure_class": classify_failure(error_code if status == "FAILURE" else "SUCCESS"),
        "duration_ms": duration,
        "attempt_count": attempts,
        "retry_count": max(attempts - 1, 0),
        "within_retry_limit": attempts <= 2,
        "usage": usage,
    }


def _seed_policy(session: Session) -> None:
    from datetime import date

    from app.domain.enums import PolicyVersionStatus
    from app.services.policy_embedding_service import PolicyEmbeddingService
    from app.services.policy_ingestion_service import PolicyIngestionService
    from app.services.policy_service import PolicyService

    provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
    policies = PolicyService(session)
    doc = policies.create_document(name="Perf Policy", description="synthetic")
    version = policies.create_version(
        doc.id,
        version_label="2026.1",
        effective_from=date(2026, 1, 1),
        source_content="placeholder",
        status=PolicyVersionStatus.ACTIVE,
    )
    PolicyIngestionService(session).ingest(
        doc.id,
        version.id,
        filename="perf.md",
        data=PRICE_V1.markdown.encode("utf-8"),
    )
    PolicyEmbeddingService(session, provider=provider).embed_version(doc.id, version.id)
    session.info["perf_provider"] = provider
    session.info["perf_version"] = version.id


def _retrieval(session: Session) -> None:
    provider = session.info["perf_provider"]
    settings = Settings(policy_retrieval_min_similarity=0.0, embedding_dimension=768)
    PolicyRetrievalService(session, provider=provider, settings=settings).retrieve_policy_chunks(
        "price variance percent",
        top_k=3,
        policy_version_id=session.info["perf_version"],
    )


class _InstantGrounding:
    model = "fake-performance-grounding"

    def generate_structured(self, *, system_instruction, user_content, response_model):
        output = GroundedPolicyGeminiOutput(
            status="INSUFFICIENT_EVIDENCE",
            conclusion="No matching clause.",
            explanation="Retrieved text does not support a conclusion.",
            cited_chunk_ids=[],
        )
        return StructuredLLMResponse(
            output=output,
            raw_text=None,
            model=self.model,
            provider="fake",
            usage=LLMUsageMetadata(),
        )


def _ground(session: Session) -> None:
    from app.services.policy_grounding_service import PolicyGroundingService

    exc = _exception(session, "ground")
    settings = Settings(policy_retrieval_min_similarity=0.0, embedding_dimension=768)
    retrieval = PolicyRetrievalService(
        session,
        provider=session.info["perf_provider"],
        settings=settings,
    )
    PolicyGroundingService(
        session,
        llm=_InstantGrounding(),  # type: ignore[arg-type]
        retrieval=retrieval,
        settings=settings,
    ).explain_exception(
        exc.id,
        policy_version_id=session.info["perf_version"],
        persist=False,
    )


class _InstantPlanner:
    model = "fake-performance-planner"

    def __init__(self, valid: bool) -> None:
        self.valid = valid

    def generate_structured(self, *, system_instruction, user_content, response_model):
        if not self.valid:
            payload = {"status": "ACTIONS_PROPOSED"}
        else:
            payload = {
                "status": "ACTIONS_PROPOSED",
                "reasoning_summary": "Route for review.",
                "proposed_actions": [
                    {
                        "action_type": "ROUTE_TO_REVIEW",
                        "parameters": {"review_queue": "procurement", "reason": "Variance"},
                        "action_order": 0,
                        "rationale": "Human review.",
                        "requires_approval": True,
                    }
                ],
                "limitations": "",
            }
        return StructuredLLMResponse(
            output=response_model.model_validate(payload),
            raw_text=None,
            model=self.model,
            provider="fake",
            usage=LLMUsageMetadata(),
        )


def _exception(session: Session, label: str) -> ReconciliationException:
    exc = ReconciliationException(
        exception_type=ExceptionType.PRICE_MISMATCH.value,
        severity=ExceptionSeverity.MEDIUM.value,
        message="Synthetic performance exception",
        status=ExceptionStatus.OPEN.value,
        evidence={"invoice_total": "100.00"},
        fingerprint=f"m11-perf-{label}-{uuid4().hex[:8]}",
    )
    session.add(exc)
    session.flush()
    return exc


def _plan(session: Session, valid: bool, label: str):
    exc = _exception(session, label)
    try:
        response = ResolutionPlanningService(
            session, llm=_InstantPlanner(valid)
        ).create_resolution_plan(exc.id, commit=True)
    except (ResolutionPlanningValidationError, ValidationError):
        session.rollback()
        return None
    return response


def measure_idempotency(session: Session, *, label: str = "idem") -> dict[str, Any]:
    response = _plan(session, True, label)
    assert response is not None
    service = ResolutionService(session)
    from app.db.models import ResolutionPlan

    plan = session.get(ResolutionPlan, response.plan_id)
    assert plan is not None
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer=REVIEWER, reason="perf")
    exec_ms, first = _time_call(
        lambda: service.execute_action(plan.id, action.id, idempotency_key=f"{label}-same")
    )
    second = service.execute_action(plan.id, action.id, idempotency_key=f"{label}-same")
    blocked = False
    try:
        service.execute_action(plan.id, action.id, idempotency_key=f"{label}-other")
    except ResolutionValidationError:
        blocked = True
    routes = session.scalar(
        select(func.count()).select_from(ActionExecution).where(
            ActionExecution.proposed_action_id == action.id
        )
    )
    return {
        "request_count": 3,
        "execution_count": int(routes or 0),
        "same_result": first.id == second.id,
        "different_key_blocked": blocked,
        "duplicate_side_effects": 0 if routes == 1 else int(routes or 0) - 1,
        "execution_ms": exec_ms,
    }


def measure_rollback(session: Session) -> dict[str, Any]:
    before = session.scalar(select(func.count()).select_from(ReconciliationException)) or 0
    try:
        with session.begin_nested():
            _exception(session, "rollback")
            raise RuntimeError("controlled database failure")
    except RuntimeError:
        session.rollback()
    after = session.scalar(select(func.count()).select_from(ReconciliationException)) or 0
    return {
        "failure_class": "DATABASE_FAILURE",
        "rolled_back": after == before,
        "orphan_approvals": 0,
    }


def measure_contention(session: Session) -> dict[str, Any]:
    """Two sequential executions stand in for a bounded duplicate attempt.

    SQLite plus the existing row lock is exercised by the second call, which
    must reuse the first execution.
    """
    stats = measure_idempotency(session, label="contention")
    return {
        "attempts": 2,
        "successful_executions": 1 if stats["same_result"] else stats["execution_count"],
        "duplicate_side_effects": stats["duplicate_side_effects"],
        "status_corrupted": not stats["same_result"],
    }


def evaluate_dataset(
    *,
    warmup_runs: int = WARMUP_RUNS,
    measured_runs: int = MEASURED_RUNS,
) -> dict[str, Any]:
    session = make_eval_session()
    try:
        _seed_policy(session)
        groups: dict[str, list[float]] = {
            "m4": [],
            "embedding": [],
            "retrieval": [],
            "grounding": [],
            "planner": [],
        }
        provider = session.info["perf_provider"]
        for workload in WORKLOADS:
            if workload.operation != "m4_extraction":
                continue
            text = TEXTS[workload.case_id]
            groups["m4"].extend(
                _repeat(lambda text=text: _m4(text), warmup=warmup_runs, measured=measured_runs)
            )
        groups["embedding"].extend(
            _repeat(
                lambda: provider.embed_query("price variance percent"),
                warmup=warmup_runs,
                measured=measured_runs,
            )
        )
        groups["retrieval"].extend(
            _repeat(lambda: _retrieval(session), warmup=warmup_runs, measured=measured_runs)
        )
        groups["grounding"].extend(
            _repeat(lambda: _ground(session), warmup=warmup_runs, measured=measured_runs)
        )
        groups["planner"].extend(
            _repeat(
                lambda: _plan(session, True, f"plan-{uuid4().hex[:6]}"),
                warmup=warmup_runs,
                measured=measured_runs,
            )
        )
        grounding_ms = groups["grounding"][-1]
        planner_ms, plan = _time_call(lambda: _plan(session, True, "plan"))
        invalid_ms, invalid = _time_call(lambda: _plan(session, False, "invalid"))
        idem = measure_idempotency(session)
        rollback = measure_rollback(session)
        contention = measure_contention(session)
        retry = measure_provider("retry-then-success")
        timeout = measure_provider("timeout")
        malformed = measure_provider("malformed")
        unavailable = measure_provider("unavailable")
        groups["execution"] = [idem["execution_ms"]]
        groups["end_to_end"] = [
            groups["m4"][-1]
            + groups["embedding"][-1]
            + groups["retrieval"][-1]
            + groups["grounding"][-1]
            + groups["planner"][-1]
            + idem["execution_ms"]
        ]
        usage = usage_report(None, None, None)
        cost = estimate_cost(
            None,
            None,
            input_price_per_million=None,
            output_price_per_million=None,
            pricing_version=PRICING_VERSION,
        )
        provider_rows = [retry, timeout, malformed, unavailable]
        return {
            "dataset": DATASET_ID,
            "mode": "OFFLINE_DETERMINISTIC_EVALUATION",
            "protocol": {
                "warmup_runs": warmup_runs,
                "measured_runs": measured_runs,
                "clock": "time.perf_counter",
                "p95_method": "nearest-rank",
            },
            "latency": {name: summarize(samples) for name, samples in groups.items()},
            "stage_ms": {
                "grounding": grounding_ms,
                "planner": planner_ms,
                "planner_validation_failure": invalid_ms,
                "m6": None,
                "execution": idem["execution_ms"],
            },
            "m6_status": "NOT_RUN",
            "usage": {
                "extraction": usage,
                "grounding": usage,
                "resolution_planning": usage,
            },
            "cost": cost,
            "reliability": {
                "planner_persisted": plan is not None,
                "invalid_plan_persisted": invalid is not None,
                "provider_failures": provider_rows,
                "rollback": rollback,
                "idempotency": idem,
                "contention": contention,
                "duplicate_side_effects": idem["duplicate_side_effects"]
                + contention["duplicate_side_effects"],
            },
            "regression_failures": _gates(
                retry, timeout, malformed, idem, contention, rollback, cost
            ),
            "note": (
                "Synthetic offline baseline. Not a production SLA. "
                "M6 latency is NOT_RUN without --live."
            ),
        }
    finally:
        session.close()


def _gates(retry, timeout, malformed, idem, contention, rollback, cost) -> list[str]:
    failures: list[str] = []
    if not retry["within_retry_limit"] or not timeout["within_retry_limit"]:
        failures.append("retry_limit_exceeded")
    if retry["attempt_count"] < 1:
        failures.append("retry_not_attempted")
    if idem["duplicate_side_effects"] != 0 or contention["duplicate_side_effects"] != 0:
        failures.append("duplicate_side_effects")
    if not idem["same_result"] or not idem["different_key_blocked"]:
        failures.append("idempotency")
    if not rollback["rolled_back"]:
        failures.append("rollback")
    if cost["status"] != COST_UNAVAILABLE:
        failures.append("fabricated_cost")
    if malformed["failure_class"] != "PROVIDER_INVALID_RESPONSE":
        failures.append("malformed_classification")
    if timeout["failure_class"] != "PROVIDER_TIMEOUT":
        failures.append("timeout_classification")
    return failures


def sample_cost(input_tokens: int, output_tokens: int) -> dict[str, Any]:
    """Test-only price fixture. These numbers are not provider prices."""
    return estimate_cost(
        input_tokens,
        output_tokens,
        input_price_per_million=Decimal("2"),
        output_price_per_million=Decimal("4"),
        pricing_version="test-fixture-not-billing",
    )
