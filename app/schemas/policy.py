"""API schemas for the M7.1 policy knowledge base (no embeddings)."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import PolicyVersionStatus


class PolicyDocumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class PolicyDocumentRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class PolicyDocumentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PolicyDocumentRead]
    count: int


class PolicyVersionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version_label: str = Field(min_length=1, max_length=64)
    title: str | None = Field(default=None, max_length=255)
    status: PolicyVersionStatus = PolicyVersionStatus.DRAFT
    effective_from: date
    effective_to: date | None = None
    source_filename: str | None = Field(default=None, max_length=512)
    source_reference: str | None = Field(default=None, max_length=512)
    # Raw source text used to compute content_hash when hash not supplied.
    source_content: str | None = None
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)


class PolicyChunkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_index: int = Field(ge=0)
    section_id: str | None = Field(default=None, max_length=128)
    section_title: str | None = Field(default=None, max_length=512)
    content: str = Field(min_length=1)
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    source_filename: str | None = Field(default=None, max_length=512)
    page_number: int | None = Field(default=None, ge=1)


class PolicyChunkBatchCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunks: list[PolicyChunkCreate] = Field(min_length=1)


class PolicyChunkRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    policy_version_id: UUID
    chunk_index: int
    section_id: str | None
    section_title: str | None
    content: str
    content_hash: str
    source_filename: str | None
    page_number: int | None
    created_at: datetime
    updated_at: datetime


class PolicyChunkListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PolicyChunkRead]
    count: int


class PolicyVersionRead(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    policy_document_id: UUID
    version_label: str
    title: str | None
    status: PolicyVersionStatus
    effective_from: date
    effective_to: date | None
    source_filename: str | None
    source_reference: str | None
    content_hash: str
    created_at: datetime
    updated_at: datetime


class PolicyVersionListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PolicyVersionRead]
    count: int


class PolicyVersionDetailRead(PolicyVersionRead):
    """Version metadata plus ordered chunks for citation-ready retrieval."""

    chunks: list[PolicyChunkRead] = Field(default_factory=list)
