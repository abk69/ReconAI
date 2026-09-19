"""M7.5 RAG evaluation runner — retrieval + grounding, offline by default.

Usage (offline, no API key):
    python -m app.evaluation.m7_runner

Usage (optional tiny live RAG smoke):
    python -m app.evaluation.m7_runner --live
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import models as _models  # noqa: F401
from app.db.base import Base
from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_corpus import seed_eval_corpus
from app.evaluation.m7_golden import DATASET_ID, dataset_summary
from app.evaluation.m7_grounding_eval import PolicyGroundingEvaluator
from app.evaluation.m7_retrieval_eval import PolicyRetrievalEvaluator


def _make_session() -> Session:
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


def run_offline_evaluation() -> dict[str, Any]:
    session = _make_session()
    try:
        provider = FakeEmbeddingProvider(model="fake-embedding-eval", dimension=768)
        corpus = seed_eval_corpus(session, embedding_provider=provider)
        retrieval_report = PolicyRetrievalEvaluator(
            session, corpus=corpus, embedding_provider=provider
        ).evaluate()
        grounding_report = PolicyGroundingEvaluator(
            session, corpus=corpus, embedding_provider=provider
        ).evaluate()
        return {
            "dataset": DATASET_ID,
            "summary": dataset_summary(),
            "cases": grounding_report["cases"],
            "retrieval": retrieval_report["retrieval"],
            "grounding": grounding_report["grounding"],
            "retrieval_case_results": retrieval_report["case_results"],
            "grounding_case_results": grounding_report["case_results"],
            "note": (
                "Offline evaluation uses FakeEmbeddingProvider + FakeGroundingLLM. "
                "Retrieval and grounding are scored separately — no single overall RAG score. "
                "Pass --live for a bounded live smoke (requires GEMINI_API_KEY)."
            ),
        }
    finally:
        session.close()


def run_live_smoke() -> dict[str, Any]:
    """Bounded live smoke: one retrieval + one grounded explanation."""
    import os
    from datetime import date
    from uuid import uuid4

    from app.core.config import Settings, get_settings
    from app.db.models import ReconciliationException
    from app.domain.enums import (
        ExceptionSeverity,
        ExceptionStatus,
        ExceptionType,
        PolicyVersionStatus,
    )
    from app.embeddings.gemini import GeminiEmbeddingProvider
    from app.evaluation.m7_golden import PRICE_V1
    from app.llm.gemini import GeminiProvider
    from app.services.policy_embedding_service import PolicyEmbeddingService
    from app.services.policy_grounding_service import PolicyGroundingService
    from app.services.policy_ingestion_service import PolicyIngestionService
    from app.services.policy_retrieval_service import PolicyRetrievalService
    from app.services.policy_service import PolicyService

    get_settings.cache_clear()
    api_key = os.environ.get("GEMINI_API_KEY") or get_settings().gemini_api_key
    if not api_key:
        return {"error": "GEMINI_API_KEY not configured"}

    settings = Settings(
        gemini_api_key=api_key,
        embedding_model="gemini-embedding-001",
        embedding_dimension=768,
        llm_model="gemini-3.1-flash-lite",
        policy_retrieval_min_similarity=0.15,
        policy_grounding_top_k=3,
    )
    session = _make_session()
    try:
        svc = PolicyService(session)
        doc = svc.create_document(name=f"LiveEval-{uuid4().hex[:8]}")
        version = svc.create_version(
            doc.id,
            version_label="live-1",
            effective_from=date(2026, 1, 1),
            source_content="placeholder",
            status=PolicyVersionStatus.ACTIVE,
        )
        PolicyIngestionService(session).ingest(
            doc.id, version.id, filename="price.md", data=PRICE_V1.markdown.encode("utf-8")
        )
        embed = GeminiEmbeddingProvider(settings)
        PolicyEmbeddingService(session, provider=embed, settings=settings).embed_version(
            doc.id, version.id
        )
        retrieval = PolicyRetrievalService(session, provider=embed, settings=settings)
        hits = retrieval.retrieve_policy_chunks(
            "unit price variance two percent",
            top_k=3,
            policy_version_id=version.id,
        )
        exc = ReconciliationException(
            exception_type=ExceptionType.PRICE_MISMATCH.value,
            severity=ExceptionSeverity.HIGH.value,
            message="Unit price variance",
            status=ExceptionStatus.OPEN.value,
            evidence={"percentage_variance": "5.0"},
            fingerprint=f"live-eval-{uuid4().hex}",
            source_document_ids=[],
        )
        session.add(exc)
        session.commit()
        grounded = PolicyGroundingService(
            session,
            llm=GeminiProvider(settings),
            retrieval=PolicyRetrievalService(session, provider=embed, settings=settings),
            settings=settings,
        ).explain_exception(exc.id, policy_version_id=version.id, persist=False)
        return {
            "dataset": DATASET_ID,
            "live": True,
            "retrieval_hit_count": len(hits),
            "grounding_status": grounded.status.value,
            "citation_count": len(grounded.citations),
            "exception_status_unchanged": session.get(
                ReconciliationException, exc.id
            ).status
            == ExceptionStatus.OPEN.value,
        }
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="ReconAI M7.5 policy RAG evaluation")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run a bounded live Gemini RAG smoke (requires GEMINI_API_KEY)",
    )
    args = parser.parse_args()
    report = run_live_smoke() if args.live else run_offline_evaluation()
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
