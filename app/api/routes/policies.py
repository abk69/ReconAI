"""Policy knowledge-base API routes (M7.1)."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.policy import (
    PolicyChunkBatchCreate,
    PolicyChunkListResponse,
    PolicyChunkRead,
    PolicyDocumentCreate,
    PolicyDocumentListResponse,
    PolicyDocumentRead,
    PolicyVersionCreate,
    PolicyVersionDetailRead,
    PolicyVersionListResponse,
    PolicyVersionRead,
)
from app.services.policy_service import (
    PolicyConflictError,
    PolicyNotFoundError,
    PolicyService,
    PolicyValidationError,
)

router = APIRouter(prefix="/policies", tags=["policies"])
DbSession = Annotated[Session, Depends(get_db)]


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
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.post("", response_model=PolicyDocumentRead, status_code=status.HTTP_201_CREATED)
def create_policy(body: PolicyDocumentCreate, session: DbSession) -> PolicyDocumentRead:
    try:
        doc = PolicyService(session).create_document(name=body.name, description=body.description)
    except (PolicyConflictError, PolicyValidationError) as exc:
        raise _http_error(exc) from exc
    return PolicyDocumentRead.model_validate(doc)


@router.get("", response_model=PolicyDocumentListResponse)
def list_policies(session: DbSession) -> PolicyDocumentListResponse:
    items = [PolicyDocumentRead.model_validate(d) for d in PolicyService(session).list_documents()]
    return PolicyDocumentListResponse(items=items, count=len(items))


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
    items = [PolicyVersionRead.model_validate(v) for v in versions]
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
