"""API schemas for document intake."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import DocumentStatus, DocumentType


class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    original_filename: str
    stored_filename: str
    document_type: DocumentType
    mime_type: str
    file_extension: str
    file_size: int
    sha256: str
    storage_path: str
    status: DocumentStatus
    vendor_id: UUID | None = None
    purchase_order_id: UUID | None = None
    goods_receipt_id: UUID | None = None
    invoice_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    is_duplicate: bool = False


class DocumentUpdateRequest(BaseModel):
    """Optional metadata / association update (no file body)."""

    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType | None = None
    vendor_id: UUID | None = None
    purchase_order_id: UUID | None = None
    goods_receipt_id: UUID | None = None
    invoice_id: UUID | None = None


class DocumentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DocumentResponse] = Field(default_factory=list)
    count: int
    total: int
