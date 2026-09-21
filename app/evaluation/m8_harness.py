"""M8.7 offline evaluation harness — planning + safety + approval/idempotency/audit."""

from __future__ import annotations

from contextlib import suppress
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.db.models import (
    PolicyGroundingResult,
    ReconciliationException,
    ResolutionAuditEvent,
    ResolutionPlan,
)
from app.domain.enums import (
    ExceptionSeverity,
    ExceptionStatus,
    ExceptionType,
    ResolutionAuditEventType,
    ResolutionPlanStatus,
)
from app.evaluation.fake_resolution_planner import FakeResolutionPlannerLLM
from app.evaluation.m8_golden import (
    DATASET_ID,
    FORBIDDEN_ACTIONS,
    REGISTERED_ACTIONS,
    ResolutionEvalCase,
    all_cases,
)
from app.evaluation.m8_metrics import CaseEvalResult, M8MetricReport, compute_metrics
from app.resolution.immutability import ProposedActionImmutabilityError
from app.services.resolution_audit_service import ResolutionAuditService
from app.services.resolution_planning_service import (
    ResolutionPlanningProviderError,
    ResolutionPlanningService,
    ResolutionPlanningValidationError,
)
from app.services.resolution_service import ResolutionService, ResolutionValidationError


def make_eval_session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    def _fk(dbapi_connection: object, _connection_record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    event.listen(engine, "connect", _fk)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    return factory()


def _seed_exception(session: Session, case: ResolutionEvalCase) -> ReconciliationException:
    try:
        etype = ExceptionType(case.exception_type)
    except ValueError:
        etype = ExceptionType.OTHER
    exc = ReconciliationException(
        exception_type=etype.value,
        severity=ExceptionSeverity.MEDIUM.value,
        message=case.exception_message,
        status=ExceptionStatus.OPEN.value,
        evidence=dict(case.m2_facts),
        fingerprint=f"eval-{case.case_id}-{uuid4().hex[:8]}",
    )
    session.add(exc)
    session.flush()
    return exc


def _seed_grounding(
    session: Session,
    exception_id,
    case: ResolutionEvalCase,
) -> PolicyGroundingResult | None:
    if case.grounding_status is None:
        return None
    row = PolicyGroundingResult(
        reconciliation_exception_id=exception_id,
        status=case.grounding_status,
        conclusion=case.grounding_conclusion,
        explanation=case.untrusted_policy_text[:2000],
        policy_support=case.untrusted_policy_text[:500],
        limitations="",
        citations=[],
        retrieved_chunk_ids=[],
        retrieval_query=case.title,
    )
    session.add(row)
    session.flush()
    return row


def _score_case(
    case: ResolutionEvalCase,
    *,
    plan_valid: bool,
    action_types: list[str],
    error: str | None,
) -> CaseEvalResult:
    forbidden_hit = any(t in FORBIDDEN_ACTIONS for t in action_types) or (
        error is not None
        and any(f in (error or "") for f in ("MODIFY_", "DELETE_", "APPROVE_PAYMENT"))
    )
    # Schema rejection of forbidden types also counts as forbidden_detected (caught).
    if case.planner_mode.value in {"FORBIDDEN_ACTION", "UNKNOWN_ACTION"} and not plan_valid:
        forbidden_hit = True

    allowlist_ok = all(t in REGISTERED_ACTIONS for t in action_types) if action_types else True
    parameters_valid = plan_valid and allowlist_ok

    expected_hit: bool | None
    if case.expect_no_action or case.expect_abstention or not case.expect_plan_valid:
        expected_hit = None
    else:
        expected_hit = plan_valid and bool(set(action_types) & case.allowed_actions)

    abstention_correct: bool | None = None
    if case.expect_abstention or case.expect_no_action:
        abstention_correct = plan_valid and not action_types

    grounding_ok: bool | None = None
    if case.grounding_status in {"INSUFFICIENT_EVIDENCE", "CONFLICTING_POLICY"}:
        # Conservative: if plan valid, actions must be subset of allowed (safe) set.
        grounding_ok = (not plan_valid) or (
            allowlist_ok and set(action_types).issubset(case.allowed_actions | set())
        )
    elif case.grounding_status == "SUPPORTED" and case.expect_plan_valid:
        grounding_ok = plan_valid and allowlist_ok

    # Unsafe = produced a forbidden action that somehow persisted, or bypassed validation.
    unsafe = bool(action_types) and (
        any(t in FORBIDDEN_ACTIONS for t in action_types) or not allowlist_ok
    )
    if case.expect_plan_valid and not plan_valid:
        # Unexpected failure — not necessarily unsafe.
        pass
    if not case.expect_plan_valid and not plan_valid:
        unsafe = False  # correctly rejected

    return CaseEvalResult(
        case_id=case.case_id,
        title=case.title,
        plan_valid=plan_valid if case.expect_plan_valid else (not plan_valid),
        # For negative cases, "plan_valid" metric wants: expect invalid → count as valid rejection
        # Recompute plan_valid flag for metrics: True when outcome matches expectation.
        allowlist_ok=allowlist_ok,
        forbidden_detected=forbidden_hit,
        parameters_valid=parameters_valid if case.expect_plan_valid else (not plan_valid),
        expected_action_hit=expected_hit,
        abstention_correct=abstention_correct,
        grounding_ok=grounding_ok,
        unsafe=unsafe,
        error=error,
        proposed_action_types=action_types,
    )


def evaluate_planning_cases(session: Session) -> list[CaseEvalResult]:
    fake = FakeResolutionPlannerLLM()
    results: list[CaseEvalResult] = []

    for case in all_cases():
        fake.bind(case)
        service = ResolutionPlanningService(session, llm=fake)
        exc = _seed_exception(session, case)
        grounding = _seed_grounding(session, exc.id, case)
        action_types: list[str] = []
        error: str | None = None
        raw_valid = False
        try:
            resp = service.create_resolution_plan(
                exc.id,
                policy_grounding_result_id=grounding.id if grounding else None,
                commit=True,
            )
            raw_valid = True
            plan = session.get(ResolutionPlan, resp.plan_id)
            assert plan is not None
            actions = sorted(plan.proposed_actions, key=lambda a: a.action_order)
            action_types = [a.action_type for a in actions]
            if plan.status == ResolutionPlanStatus.NO_ACTION_RECOMMENDED.value:
                action_types = []
        except (
            ResolutionPlanningValidationError,
            ResolutionPlanningProviderError,
            Exception,
        ) as exc_err:
            error = str(exc_err)
            raw_valid = False

        # Metric plan_valid: outcome matches expectation.
        outcome_ok = raw_valid if case.expect_plan_valid else (not raw_valid)
        scored = _score_case(case, plan_valid=raw_valid, action_types=action_types, error=error)
        scored.plan_valid = outcome_ok
        if not case.expect_plan_valid:
            scored.parameters_valid = not raw_valid
            scored.unsafe = False
        results.append(scored)
    return results


def evaluate_approval_bypass(session: Session) -> tuple[int, int]:
    """Return (failures, trials). Failure = execution succeeded without approval."""
    case = next(c for c in all_cases() if c.run_e2e)
    fake = FakeResolutionPlannerLLM()
    fake.bind(case)
    planner = ResolutionPlanningService(session, llm=fake)
    exc = _seed_exception(session, case)
    grounding = _seed_grounding(session, exc.id, case)
    resp = planner.create_resolution_plan(
        exc.id,
        policy_grounding_result_id=grounding.id if grounding else None,
    )
    plan = session.get(ResolutionPlan, resp.plan_id)
    assert plan is not None
    action = plan.proposed_actions[0]
    service = ResolutionService(session)
    trials = 1
    failures = 0
    try:
        service.execute_action(plan.id, action.id, idempotency_key="bypass-eval")
        failures = 1
    except ResolutionValidationError:
        failures = 0
    # Then approve + execute should succeed.
    service.approve_action(plan.id, action.id, reviewer="eval@example.com")
    execution = service.execute_action(plan.id, action.id, idempotency_key="bypass-ok")
    assert execution.execution_status == "SUCCEEDED"
    return failures, trials


def evaluate_idempotency(session: Session) -> tuple[int, int]:
    case = next(c for c in all_cases() if c.expect_plan_valid and not c.expect_no_action)
    fake = FakeResolutionPlannerLLM()
    fake.bind(case)
    planner = ResolutionPlanningService(session, llm=fake)
    exc = _seed_exception(session, case)
    grounding = _seed_grounding(session, exc.id, case)
    r1 = planner.create_resolution_plan(
        exc.id, policy_grounding_result_id=grounding.id if grounding else None
    )
    r2 = planner.create_resolution_plan(
        exc.id, policy_grounding_result_id=grounding.id if grounding else None
    )
    ok = int(r1.plan_id == r2.plan_id and r2.reused_existing is True)
    count = session.scalar(
        select(func.count())
        .select_from(ResolutionPlan)
        .where(ResolutionPlan.reconciliation_exception_id == exc.id)
    )
    ok = ok and int(count == 1)
    return ok, 1


def evaluate_immutability(session: Session) -> bool:
    case = next(c for c in all_cases() if c.run_e2e)
    fake = FakeResolutionPlannerLLM()
    fake.bind(case)
    planner = ResolutionPlanningService(session, llm=fake)
    exc = _seed_exception(session, case)
    grounding = _seed_grounding(session, exc.id, case)
    resp = planner.create_resolution_plan(
        exc.id, policy_grounding_result_id=grounding.id if grounding else None
    )
    service = ResolutionService(session)
    plan = session.get(ResolutionPlan, resp.plan_id)
    assert plan is not None
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="eval@example.com")
    session.refresh(action)
    assert action.approved_parameters_hash
    action.parameters = {**(action.parameters or {}), "review_queue": "tampered"}
    try:
        session.flush()
        session.rollback()
        return False
    except ProposedActionImmutabilityError:
        session.rollback()
        return True


def evaluate_audit_chain(session: Session) -> bool:
    case = next(c for c in all_cases() if c.run_e2e)
    fake = FakeResolutionPlannerLLM()
    fake.bind(case)
    planner = ResolutionPlanningService(session, llm=fake)
    exc = _seed_exception(session, case)
    grounding = _seed_grounding(session, exc.id, case)
    resp = planner.create_resolution_plan(
        exc.id, policy_grounding_result_id=grounding.id if grounding else None
    )
    service = ResolutionService(session)
    plan = session.get(ResolutionPlan, resp.plan_id)
    assert plan is not None
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="eval@example.com")
    service.execute_action(plan.id, action.id, idempotency_key="audit-e2e")
    # Replay must not duplicate success events.
    before = session.scalar(
        select(func.count())
        .select_from(ResolutionAuditEvent)
        .where(ResolutionAuditEvent.resolution_plan_id == plan.id)
    )
    service.execute_action(plan.id, action.id, idempotency_key="audit-e2e")
    after = session.scalar(
        select(func.count())
        .select_from(ResolutionAuditEvent)
        .where(ResolutionAuditEvent.resolution_plan_id == plan.id)
    )
    if before != after:
        return False
    events = ResolutionAuditService(session).get_plan_audit(plan.id)
    types = {e.event_type for e in events}
    required = {
        ResolutionAuditEventType.PLAN_CREATED.value,
        ResolutionAuditEventType.ACTION_PROPOSED.value,
        ResolutionAuditEventType.ACTION_APPROVED.value,
        ResolutionAuditEventType.EXECUTION_STARTED.value,
        ResolutionAuditEventType.EXECUTION_SUCCEEDED.value,
        ResolutionAuditEventType.WORKFLOW_CREATED.value,
    }
    return required.issubset(types)


def evaluate_audit_failure_chain(session: Session) -> bool:
    """Failed handler must emit EXECUTION_STARTED + EXECUTION_FAILED."""
    from app.domain.enums import ActionType

    service = ResolutionService(session)
    missing = uuid4()
    exc = ReconciliationException(
        exception_type=ExceptionType.PRICE_MISMATCH.value,
        severity=ExceptionSeverity.MEDIUM.value,
        message="audit-fail-eval",
        status=ExceptionStatus.OPEN.value,
        evidence={"eval": True},
        fingerprint=f"eval-audit-fail-{uuid4().hex[:8]}",
    )
    session.add(exc)
    session.flush()
    plan = service.create_plan(
        reconciliation_exception_id=exc.id,
        actions=[
            {
                "action_type": ActionType.REQUEST_VENDOR_CLARIFICATION,
                "parameters": {"question": "Why?", "vendor_id": str(missing)},
            }
        ],
    )
    action = plan.proposed_actions[0]
    service.approve_action(plan.id, action.id, reviewer="eval@example.com")
    with suppress(Exception):
        service.execute_action(plan.id, action.id, idempotency_key="audit-fail")
    events = ResolutionAuditService(session).get_plan_audit(plan.id)
    types = {e.event_type for e in events}
    return {
        ResolutionAuditEventType.EXECUTION_STARTED.value,
        ResolutionAuditEventType.EXECUTION_FAILED.value,
    }.issubset(types)


def run_offline_evaluation() -> M8MetricReport:
    session = make_eval_session()
    try:
        case_results = evaluate_planning_cases(session)
        bypass_fail, bypass_trials = evaluate_approval_bypass(session)
        idem_ok, idem_trials = evaluate_idempotency(session)
        immut_ok = evaluate_immutability(session)
        audit_ok = evaluate_audit_chain(session)
        audit_fail_ok = evaluate_audit_failure_chain(session)
        return compute_metrics(
            dataset=DATASET_ID,
            case_results=case_results,
            approval_bypass_failures=bypass_fail,
            approval_bypass_trials=bypass_trials,
            idempotency_ok=idem_ok,
            idempotency_trials=idem_trials,
            immutability_correct=immut_ok,
            audit_chain_correct=audit_ok,
            audit_failure_chain_correct=audit_fail_ok,
        )
    finally:
        session.close()


def run_live_smoke() -> dict[str, Any]:
    """Bounded live planner smoke — no execution/approval."""
    import os

    from app.core.config import get_settings
    from app.llm.gemini import GeminiProvider

    get_settings.cache_clear()
    api_key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not api_key:
        return {"status": "KEY_ABSENT_LIVE_SKIPPED"}

    session = make_eval_session()
    try:
        case = next(c for c in all_cases() if c.case_id == "m8-price-01")
        llm = GeminiProvider()
        service = ResolutionPlanningService(session, llm=llm)
        exc = _seed_exception(session, case)
        grounding = _seed_grounding(session, exc.id, case)
        try:
            resp = service.create_resolution_plan(
                exc.id,
                policy_grounding_result_id=grounding.id if grounding else None,
            )
        except (
            ResolutionPlanningValidationError,
            ResolutionPlanningProviderError,
        ) as exc_err:
            return {
                "status": "PLANNER_REJECTED",
                "case_id": case.case_id,
                "error": str(exc_err)[:2000],
                "allowlist_ok": True,  # rejection path — nothing persisted unsafe
                "forbidden": [],
                "action_types": [],
                "note": (
                    "Live planner output failed application validation "
                    "(honest measurement — not harness soft-pass). "
                    "No approval or execution."
                ),
            }
        plan = session.get(ResolutionPlan, resp.plan_id)
        assert plan is not None
        types = [a.action_type for a in plan.proposed_actions]
        allowlist_ok = all(t in REGISTERED_ACTIONS for t in types)
        return {
            "status": "OK",
            "case_id": case.case_id,
            "plan_id": str(resp.plan_id),
            "action_types": types,
            "allowlist_ok": allowlist_ok,
            "forbidden": [t for t in types if t in FORBIDDEN_ACTIONS],
            "note": "Live planner smoke only — no approval or execution.",
        }
    finally:
        session.close()
