"""Seed a deterministic M7 evaluation corpus (ingest + fake embeddings)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from uuid import UUID

from sqlalchemy.orm import Session

from app.domain.enums import PolicyVersionStatus
from app.embeddings.fake import FakeEmbeddingProvider
from app.evaluation.m7_golden import GOLDEN_POLICIES, GoldenPolicySource
from app.services.policy_embedding_service import PolicyEmbeddingService
from app.services.policy_ingestion_service import PolicyIngestionService
from app.services.policy_service import PolicyService


@dataclass
class SeededPolicy:
    key: str
    policy_document_id: UUID
    policy_version_id: UUID
    version_label: str
    # section_id -> chunk ids
    chunks_by_section: dict[str | None, list[UUID]] = field(default_factory=dict)
    all_chunk_ids: list[UUID] = field(default_factory=list)


@dataclass
class EvalCorpus:
    policies: dict[str, SeededPolicy]
    # Shared document for price_v2026_1 and price_v2026_2 (same name → conflict tests).
    price_document_id: UUID | None = None


def seed_eval_corpus(
    session: Session,
    *,
    embedding_provider: FakeEmbeddingProvider | None = None,
    policies: list[GoldenPolicySource] | None = None,
) -> EvalCorpus:
    """Create policy docs/versions/chunks/embeddings for the golden sources.

    Price 2026.1 and 2026.2 share one PolicyDocument so conflict detection works.
    """
    provider = embedding_provider or FakeEmbeddingProvider(
        model="fake-embedding-eval",
        dimension=768,
    )
    sources = policies or GOLDEN_POLICIES
    policy_svc = PolicyService(session)
    ingestion = PolicyIngestionService(session)
    embedding = PolicyEmbeddingService(session, provider=provider)

    seeded: dict[str, SeededPolicy] = {}
    price_doc_id: UUID | None = None

    for source in sources:
        if source.key.startswith("price_"):
            if price_doc_id is None:
                doc = policy_svc.create_document(
                    name=source.name,
                    description="M7.5 eval price policy",
                )
                price_doc_id = doc.id
            else:
                doc = policy_svc.get_document(price_doc_id)
        else:
            doc = policy_svc.create_document(
                name=source.name,
                description=f"M7.5 eval {source.key}",
            )

        status = PolicyVersionStatus(source.status)
        version = policy_svc.create_version(
            doc.id,
            version_label=source.version_label,
            effective_from=date(2026, 1, 1),
            source_content="eval-placeholder",
            status=status,
        )
        ingestion.ingest(
            doc.id,
            version.id,
            filename=f"{source.key}.md",
            data=source.markdown.encode("utf-8"),
        )
        embedding.embed_version(doc.id, version.id)
        chunks = policy_svc.list_chunks(doc.id, version.id)
        by_section: dict[str | None, list[UUID]] = {}
        for chunk in chunks:
            by_section.setdefault(chunk.section_id, []).append(chunk.id)
        seeded[source.key] = SeededPolicy(
            key=source.key,
            policy_document_id=doc.id,
            policy_version_id=version.id,
            version_label=source.version_label,
            chunks_by_section=by_section,
            all_chunk_ids=[c.id for c in chunks],
        )

    return EvalCorpus(policies=seeded, price_document_id=price_doc_id)


def resolve_expected_chunk_ids(
    corpus: EvalCorpus,
    *,
    policy_key: str | None,
    section_ids: tuple[str, ...],
    content_markers: tuple[str, ...] = (),
    session: Session | None = None,
) -> set[UUID]:
    """Map golden section/marker expectations onto seeded chunk UUIDs."""
    if not section_ids and not content_markers:
        return set()

    from app.db.models import PolicyChunk

    keys = [policy_key] if policy_key else list(corpus.policies.keys())
    expected: set[UUID] = set()
    for key in keys:
        seeded = corpus.policies.get(key)
        if seeded is None:
            continue
        for sid in section_ids:
            expected.update(seeded.chunks_by_section.get(sid, []))
        if content_markers and session is not None:
            for cid in seeded.all_chunk_ids:
                chunk = session.get(PolicyChunk, cid)
                if chunk is None:
                    continue
                text = chunk.content.casefold()
                if all(m.casefold() in text for m in content_markers):
                    expected.add(cid)
        elif content_markers:
            # Without session, section match is the only signal already applied.
            pass
    return expected
