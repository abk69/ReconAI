"""Offline RAG evaluation. Gemini runs only with --live.

    python -m app.evaluation.m11_rag_runner
    python -m app.evaluation.m11_rag_runner --live
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.evaluation.m11_rag_dataset import DATASET_ID
from app.evaluation.m11_rag_harness import evaluate_dataset


def make_session() -> Session:
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


def run_offline() -> dict[str, Any]:
    session = make_session()
    try:
        return evaluate_dataset(session)
    finally:
        session.close()


def run_live(api_key: str | None = None) -> dict[str, Any]:
    """Bounded live smoke. Offline evaluation does not call this."""
    from app.core.config import get_settings

    key = api_key
    if key is None:
        key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not key:
        return {"status": "LIVE_NOT_RUN", "dataset": DATASET_ID}
    from app.evaluation.m7_runner import run_live_smoke

    try:
        smoke = run_live_smoke()
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "LIVE_FAILED",
            "dataset": DATASET_ID,
            "error_type": type(exc).__name__,
        }
    if smoke.get("error"):
        return {"status": "LIVE_NOT_RUN", "dataset": DATASET_ID}
    return {
        "status": "OK",
        "dataset": DATASET_ID,
        "mode": "LIVE_LLM_EVALUATION",
        "model": "gemini-3.1-flash-lite",
        "retrieval_hit_count": smoke.get("retrieval_hit_count"),
        "grounding_status": smoke.get("grounding_status"),
        "citation_count": smoke.get("citation_count"),
    }


def _print_report(report: dict[str, Any]) -> None:
    print(f"Dataset: {report['dataset']}")
    print(f"Mode: {report['mode']}")
    print(f"cases_evaluated: {report['cases_evaluated']}")
    retrieval = report["retrieval"]
    for key in (
        "hit_at_1",
        "hit_at_3",
        "hit_at_5",
        "recall_at_1",
        "recall_at_3",
        "recall_at_5",
        "mrr",
    ):
        row = retrieval[key]
        print(f"{key}: {row['value']} defined_cases={row['defined_cases']}/{row['case_count']}")
    grounding = report["grounding"]
    for key in ("answer_fact_accuracy", "citation_precision", "citation_recall"):
        row = grounding[key]
        print(f"{key}: {row['value']} defined_cases={row['defined_cases']}/{row['case_count']}")
    abstain = grounding["abstention_accuracy"]
    conflict = grounding["conflict_detection"]
    print(
        f"abstention_accuracy: {abstain['correct']}/{abstain['denominator']} = {abstain['value']}"
    )
    print(
        "conflict_detection: "
        f"{conflict['correct']}/{conflict['denominator']} = {conflict['value']}"
    )
    print(f"incorrect_answer_count: {grounding['incorrect_answer_count']}")
    print(f"unsupported_answer_count: {grounding['unsupported_answer_count']}")
    security = report["security"]
    print(f"prompt_injection_cases: {security['prompt_injection_cases']}")
    print(f"unsafe_behavior_count: {security['unsafe_behavior_count']}")
    print(f"instruction_following_violations: {security['instruction_following_violations']}")
    if report["regression_failures"]:
        print("regression_failures:")
        for item in report["regression_failures"]:
            print(f"  {item}")
    else:
        print("regression_failures: none")
    print("cases:")
    for case in report["cases"]:
        print(
            f"  {case['case_id']} expected={case['expected_status']} "
            f"actual={case['actual_status']} errors={len(case['errors'])}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M11.2 RAG and grounding evaluation")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.live:
        result = run_live()
        print(json.dumps(result, indent=2, default=str))
        return 0 if result.get("status") in {"OK", "LIVE_NOT_RUN"} else 1
    report = run_offline()
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        _print_report(report)
    return 1 if report["regression_failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
