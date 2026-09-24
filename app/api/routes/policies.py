"""Policy knowledge-base API routes (M7.1 + M7.2 ingestion)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.enums import PolicyVersionStatus
from app.embeddings.base import EmbeddingProviderError
from app.schemas.policy import (
    PolicyChunkBatchCreate,
    PolicyChunkListResponse,
    PolicyChunkRead,
    PolicyDocumentCreate,
    PolicyDocumentListResponse,
    PolicyDocumentRead,
    PolicyEmbedResponse,
    PolicyIngestionResponse,
    PolicyLibraryItem,
    PolicySearchHit,
    PolicySearchRequest,
    PolicySearchResponse,
    PolicyVersionCreate,
    PolicyVersionDetailRead,
    PolicyVersionListResponse,
    PolicyVersionRead,
    PolicyVersionSummary,
)
from app.services.policy_embedding_service import PolicyEmbeddingService
from app.services.policy_ingestion_service import PolicyIngestionService
from app.services.policy_retrieval_service import PolicyRetrievalService
from app.services.policy_service import (
    PolicyConflictError,
    PolicyNotFoundError,
    PolicyService,
    PolicyValidationError,
)

router = APIRouter(prefix="/policies", tags=["policies"])
DbSession = Annotated[Session, Depends(get_db)]
UploadFileParam = Annotated[UploadFile, File()]


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PolicyNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, PolicyConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, PolicyValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        )
    if isinstance(exc, EmbeddingProviderError):
        code = status.HTTP_502_BAD_GATEWAY
        if exc.code == "MISSING_API_KEY":
            code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HTTPException(status_code=code, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("", response_model=PolicyDocumentRead, status_code=status.HTTP_201_CREATED)
def create_policy(body: PolicyDocumentCreate, session: DbSession) -> PolicyDocumentRead:
    try:
        doc = PolicyService(session).create_document(name=body.name, description=body.description)
    except (PolicyConflictError, PolicyValidationError) as exc:
        raise _http_error(exc) from exc
    return PolicyDocumentRead.model_validate(doc)


@router.get("", response_model=PolicyDocumentListResponse)
def list_policies(
    session: DbSession,
    version_status: PolicyVersionStatus | None = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> PolicyDocumentListResponse:
    page, total, grouped = PolicyService(session).list_library(
        version_status=version_status,
        limit=limit,
        offset=offset,
    )
    items: list[PolicyLibraryItem] = []
    for doc in page:
        versions = grouped.get(doc.id, [])
        active = [row for row in versions if row.status == PolicyVersionStatus.ACTIVE.value]
        chosen = active[0] if len(active) == 1 else None
        base = PolicyDocumentRead.model_validate(doc)
        items.append(
            PolicyLibraryItem(
                **base.model_dump(),
                version_count=len(versions),
                active_version_count=len(active),
                active_version_id=chosen.id if chosen else None,
                active_version_label=chosen.version_label if chosen else None,
                active_status=PolicyVersionStatus(chosen.status) if chosen else None,
                effective_from=chosen.effective_from if chosen else None,
                effective_to=chosen.effective_to if chosen else None,
            )
        )
    return PolicyDocumentListResponse(items=items, count=len(items), total=total)


@router.get("/{policy_id}", response_model=PolicyDocumentRead)
def get_policy(policy_id: UUID, session: DbSession) -> PolicyDocumentRead:
    try:
        doc = PolicyService(session).get_document(policy_id)
    except PolicyNotFoundError as exc:
        raise _http_error(exc) from exc
    return PolicyDocumentRead.model_validate(doc)


@router.post(
    "/{policy_id}/versions",
    response_model=PolicyVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_policy_version(
    policy_id: UUID,
    body: PolicyVersionCreate,
    session: DbSession,
) -> PolicyVersionRead:
    try:
        version = PolicyService(session).create_version(
            policy_id,
            version_label=body.version_label,
            title=body.title,
            status=body.status,
            effective_from=body.effective_from,
            effective_to=body.effective_to,
            source_filename=body.source_filename,
            source_reference=body.source_reference,
            source_content=body.source_content,
            content_hash=body.content_hash,
        )
    except (PolicyNotFoundError, PolicyConflictError, PolicyValidationError) as exc:
        raise _http_error(exc) from exc
    return PolicyVersionRead.model_validate(version)


@router.get("/{policy_id}/versions", response_model=PolicyVersionListResponse)
def list_policy_versions(policy_id: UUID, session: DbSession) -> PolicyVersionListResponse:
    try:
        versions = PolicyService(session).list_versions(policy_id)
    except PolicyNotFoundError as exc:
        raise _http_error(exc) from exc
    counts = PolicyService(session).chunk_counts([version.id for version in versions])
    items = [
        PolicyVersionSummary(
            **PolicyVersionRead.model_validate(version).model_dump(),
            chunk_count=counts.get(version.id, 0),
        )
        for version in versions
    ]
    return PolicyVersionListResponse(items=items, count=len(items))


@router.get("/{policy_id}/versions/{version_id}", response_model=PolicyVersionDetailRead)
def get_policy_version(
    policy_id: UUID,
    version_id: UUID,
    session: DbSession,
) -> PolicyVersionDetailRead:
    try:
        version = PolicyService(session).get_version(policy_id, version_id)
    except PolicyNotFoundError as exc:
        raise _http_error(exc) from exc
    return PolicyVersionDetailRead(
        **PolicyVersionRead.model_validate(version).model_dump(),
        chunks=[PolicyChunkRead.model_validate(c) for c in version.chunks],
    )


@router.post(
    "/{policy_id}/versions/{version_id}/chunks",
    response_model=PolicyChunkListResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_policy_chunks(
    policy_id: UUID,
    version_id: UUID,
    body: PolicyChunkBatchCreate,
    session: DbSession,
) -> PolicyChunkListResponse:
    payloads = [c.model_dump(mode="python") for c in body.chunks]
    try:
        chunks = PolicyService(session).add_chunks(policy_id, version_id, payloads)
    except (PolicyNotFoundError, PolicyConflictError, PolicyValidationError) as exc:
        raise _http_error(exc) from exc
    items = [PolicyChunkRead.model_validate(c) for c in chunks]
    return PolicyChunkListResponse(items=items, count=len(items))


@router.get(
    "/{policy_id}/versions/{version_id}/chunks",
    response_model=PolicyChunkListResponse,
)
def list_policy_chunks(
    policy_id: UUID,
    version_id: UUID,
    session: DbSession,
) -> PolicyChunkListResponse:
    try:
        chunks = PolicyService(session).list_chunks(policy_id, version_id)
    except PolicyNotFoundError as exc:
        raise _http_error(exc) from exc
    items = [PolicyChunkRead.model_validate(c) for c in chunks]
    return PolicyChunkListResponse(items=items, count=len(items))


@router.post(
    "/{policy_id}/versions/{version_id}/ingest",
    response_model=PolicyIngestionResponse,
)
async def ingest_policy_source(
    policy_id: UUID,
    version_id: UUID,
    session: DbSession,
    file: UploadFileParam,
) -> PolicyIngestionResponse:
    """Ingest a Markdown or PDF policy source into chunked PolicyChunk rows."""
    data = await file.read()
    try:
        result = PolicyIngestionService(session).ingest(
            policy_id,
            version_id,
            filename=file.filename,
            data=data,
        )
    except (PolicyNotFoundError, PolicyConflictError, PolicyValidationError) as exc:
        raise _http_error(exc) from exc
    return PolicyIngestionResponse(
        policy_id=result.policy_id,
        version_id=result.version_id,
        source_hash=result.source_hash,
        chunks_created=result.chunks_created,
        status=result.status,
        message=result.message,
    )


@router.post(
    "/{policy_id}/versions/{version_id}/embed",
    response_model=PolicyEmbedResponse,
)
def embed_policy_version(
    policy_id: UUID,
    version_id: UUID,
    session: DbSession,
) -> PolicyEmbedResponse:
    """Generate missing/stale embeddings for chunks in this version (explicit, not on GET)."""
    try:
        result = PolicyEmbeddingService(session).embed_version(policy_id, version_id)
    except (PolicyNotFoundError, PolicyValidationError, EmbeddingProviderError) as exc:
        raise _http_error(exc) from exc
    return PolicyEmbedResponse(
        policy_id=result.policy_id,
        version_id=result.version_id,
        chunks_total=result.chunks_total,
        chunks_embedded=result.chunks_embedded,
        chunks_skipped=result.chunks_skipped,
        embedding_model=result.embedding_model,
        status=result.status,
        message=result.message,
    )


@router.post(
    "/{policy_id}/versions/{version_id}/search",
    response_model=PolicySearchResponse,
)
def search_policy_version(
    policy_id: UUID,
    version_id: UUID,
    body: PolicySearchRequest,
    session: DbSession,
) -> PolicySearchResponse:
    """Vector similarity search over embedded chunks (evidence only — no generation)."""
    # Path version is the default scope; optional body override must stay on this document.
    target_version = body.policy_version_id or version_id
    try:
        PolicyService(session).get_version(policy_id, target_version)
        hits = PolicyRetrievalService(session).retrieve_policy_chunks(
            body.query,
            top_k=body.top_k,
            policy_document_id=policy_id,
            policy_version_id=target_version,
        )
    except (PolicyNotFoundError, PolicyValidationError, EmbeddingProviderError) as exc:
        raise _http_error(exc) from exc
    return PolicySearchResponse(
        query=body.query,
        top_k=body.top_k,
        items=[
            PolicySearchHit(
                chunk_id=h.chunk_id,
                policy_document_id=h.policy_document_id,
                policy_version_id=h.policy_version_id,
                chunk_index=h.chunk_index,
                content=h.content,
                section_id=h.section_id,
                section_title=h.section_title,
                page_number=h.page_number,
                source_filename=h.source_filename,
                content_hash=h.content_hash,
                embedding_model=h.embedding_model,
                distance=h.distance,
                similarity=h.similarity,
            )
            for h in hits
        ],
        count=len(hits),
    )
