"""Document intake API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.domain.enums import DocumentStatus, DocumentType
from app.schemas.documents import DocumentListResponse, DocumentResponse, DocumentUpdateRequest
from app.schemas.llm_understanding import LlmUnderstandingResponse
from app.schemas.understanding import UnderstandingResponse
from app.services.document_service import (
    DocumentAssociationError,
    DocumentNotFoundError,
    DocumentService,
    DocumentServiceError,
    DocumentValidationError,
)
from app.services.document_understanding_service import (
    DocumentUnderstandingNotFoundError,
    DocumentUnderstandingService,
)
from app.services.llm_understanding_service import (
    LlmUnderstandingNotFoundError,
    LlmUnderstandingService,
)
from app.storage.local import LocalFileStorage

router = APIRouter(prefix="/documents", tags=["documents"])
DbSession = Annotated[Session, Depends(get_db)]
UploadFileParam = Annotated[UploadFile, File()]
DocTypeForm = Annotated[DocumentType | None, Form()]
OptionalUuidForm = Annotated[UUID | None, Form()]


def _to_response(row: object, *, is_duplicate: bool = False) -> DocumentResponse:
    return DocumentResponse(
        id=row.id,  # type: ignore[attr-defined]
        original_filename=row.original_filename,  # type: ignore[attr-defined]
        stored_filename=row.stored_filename,  # type: ignore[attr-defined]
        document_type=DocumentType(row.document_type),  # type: ignore[attr-defined]
        mime_type=row.mime_type,  # type: ignore[attr-defined]
        file_extension=row.file_extension,  # type: ignore[attr-defined]
        file_size=row.file_size,  # type: ignore[attr-defined]
        sha256=row.sha256,  # type: ignore[attr-defined]
        storage_path=row.storage_path,  # type: ignore[attr-defined]
        status=DocumentStatus(row.status),  # type: ignore[attr-defined]
        vendor_id=row.vendor_id,  # type: ignore[attr-defined]
        purchase_order_id=row.purchase_order_id,  # type: ignore[attr-defined]
        goods_receipt_id=row.goods_receipt_id,  # type: ignore[attr-defined]
        invoice_id=row.invoice_id,  # type: ignore[attr-defined]
        created_at=row.created_at,  # type: ignore[attr-defined]
        updated_at=row.updated_at,  # type: ignore[attr-defined]
        is_duplicate=is_duplicate,
    )


def _document_service(session: Session) -> DocumentService:
    settings = get_settings()
    return DocumentService(session, storage=LocalFileStorage(settings.storage_root))


@router.post("")
async def upload_document(
    session: DbSession,
    file: UploadFileParam,
    document_type: DocTypeForm = None,
    vendor_id: OptionalUuidForm = None,
    purchase_order_id: OptionalUuidForm = None,
    goods_receipt_id: OptionalUuidForm = None,
    invoice_id: OptionalUuidForm = None,
) -> JSONResponse:
    """Upload and validate a procurement document (intake only; no extraction).

    Exact content duplicates return HTTP 200 with ``is_duplicate=true``.
    New uploads return HTTP 201.
    """
    data = await file.read()
    service = _document_service(session)
    try:
        row, is_duplicate = service.upload(
            filename=file.filename,
            content_type=file.content_type,
            data=data,
            document_type=document_type,
            vendor_id=vendor_id,
            purchase_order_id=purchase_order_id,
            goods_receipt_id=goods_receipt_id,
            invoice_id=invoice_id,
        )
    except DocumentValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    except DocumentAssociationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    payload = _to_response(row, is_duplicate=is_duplicate)
    code = status.HTTP_200_OK if is_duplicate else status.HTTP_201_CREATED
    return JSONResponse(status_code=code, content=payload.model_dump(mode="json"))


@router.get("", response_model=DocumentListResponse)
def list_documents(
    session: DbSession,
    document_type: DocumentType | None = None,
    doc_status: Annotated[DocumentStatus | None, Query(alias="status")] = None,
    vendor_id: UUID | None = None,
    purchase_order_id: UUID | None = None,
    invoice_id: UUID | None = None,
    goods_receipt_id: UUID | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int | None, Query(ge=1, le=100)] = None,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentListResponse:
    service = _document_service(session)
    rows, total = service.list_page(
        document_type=document_type,
        status=doc_status,
        vendor_id=vendor_id,
        purchase_order_id=purchase_order_id,
        invoice_id=invoice_id,
        goods_receipt_id=goods_receipt_id,
        q=q,
        limit=limit,
        offset=offset,
    )
    items = [_to_response(row) for row in rows]
    return DocumentListResponse(items=items, count=len(items), total=total)


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(document_id: UUID, session: DbSession) -> DocumentResponse:
    service = _document_service(session)
    try:
        row = service.get(document_id)
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row)


@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: UUID,
    body: DocumentUpdateRequest,
    session: DbSession,
) -> DocumentResponse:
    """Update document type and optional procurement associations."""
    service = _document_service(session)
    fields_set = body.model_fields_set
    try:
        row = service.update_associations(
            document_id,
            document_type=body.document_type,
            vendor_id=body.vendor_id,
            purchase_order_id=body.purchase_order_id,
            goods_receipt_id=body.goods_receipt_id,
            invoice_id=body.invoice_id,
            set_vendor="vendor_id" in fields_set,
            set_purchase_order="purchase_order_id" in fields_set,
            set_goods_receipt="goods_receipt_id" in fields_set,
            set_invoice="invoice_id" in fields_set,
        )
    except DocumentNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except DocumentAssociationError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _to_response(row)


@router.post("/{document_id}/understand", response_model=UnderstandingResponse)
def understand_document(document_id: UUID, session: DbSession) -> UnderstandingResponse:
    """Run deterministic document understanding (M4). Does not call LLMs."""
    settings = get_settings()
    service = DocumentUnderstandingService(session, storage=LocalFileStorage(settings.storage_root))
    try:
        result = service.understand(document_id)
    except DocumentUnderstandingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return UnderstandingResponse(
        document_id=result.document_id,
        detected_type=result.detected_type,
        outcome=result.outcome,
        document_status=result.document_status,
        message=result.message,
        candidate=result.candidate,
        validation=result.validation,
        evidence=result.evidence,
        extractor_version=result.extractor_version,
        has_raw_extraction=bool(result.raw_extraction),
    )


@router.get("/{document_id}/understanding", response_model=UnderstandingResponse)
def get_document_understanding(document_id: UUID, session: DbSession) -> UnderstandingResponse:
    """Return the latest persisted understanding result for a document."""
    settings = get_settings()
    service = DocumentUnderstandingService(session, storage=LocalFileStorage(settings.storage_root))
    try:
        result = service.get_understanding(document_id)
    except DocumentUnderstandingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return UnderstandingResponse(
        document_id=result.document_id,
        detected_type=result.detected_type,
        outcome=result.outcome,
        document_status=result.document_status,
        message=result.message,
        candidate=result.candidate,
        validation=result.validation,
        evidence=result.evidence,
        extractor_version=result.extractor_version,
        has_raw_extraction=bool(result.raw_extraction),
    )


def _llm_to_response(
    row: object, *, document_status: str | None = None
) -> LlmUnderstandingResponse:
    from app.domain.enums import ApplicationQuality, LlmInvocationStatus

    quality = getattr(row, "application_quality", None)
    return LlmUnderstandingResponse(
        id=row.id,  # type: ignore[attr-defined]
        document_id=row.document_id,  # type: ignore[attr-defined]
        m4_extraction_result_id=row.m4_extraction_result_id,  # type: ignore[attr-defined]
        provider=row.provider,  # type: ignore[attr-defined]
        model=row.model,  # type: ignore[attr-defined]
        prompt_version=row.prompt_version,  # type: ignore[attr-defined]
        invocation_status=LlmInvocationStatus(row.invocation_status),  # type: ignore[attr-defined]
        application_quality=ApplicationQuality(quality) if quality else None,
        quality_reasons=list(row.quality_reasons or []),  # type: ignore[attr-defined]
        gate_reasons=list(row.gate_reasons or []),  # type: ignore[attr-defined]
        candidate=row.candidate,  # type: ignore[attr-defined]
        evidence=list(row.evidence or []),  # type: ignore[attr-defined]
        validation=row.validation or {},  # type: ignore[attr-defined]
        comparison=row.comparison,  # type: ignore[attr-defined]
        evidence_check=row.evidence_check,  # type: ignore[attr-defined]
        usage=row.usage,  # type: ignore[attr-defined]
        message=row.message,  # type: ignore[attr-defined]
        error_code=row.error_code,  # type: ignore[attr-defined]
        error_message=row.error_message,  # type: ignore[attr-defined]
        document_status=document_status,
        created_at=row.created_at,  # type: ignore[attr-defined]
    )


@router.post("/{document_id}/llm-understand", response_model=LlmUnderstandingResponse)
def llm_understand_document(document_id: UUID, session: DbSession) -> LlmUnderstandingResponse:
    """Run gated Gemini assistance (M6). Never writes authoritative financial rows."""
    from app.db.models import Document

    service = LlmUnderstandingService(session)
    try:
        row = service.understand(document_id)
    except LlmUnderstandingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    document = session.get(Document, document_id)
    return _llm_to_response(
        row,
        document_status=document.status if document is not None else None,
    )


@router.get("/{document_id}/llm-understanding", response_model=LlmUnderstandingResponse)
def get_llm_understanding(document_id: UUID, session: DbSession) -> LlmUnderstandingResponse:
    """Return the latest persisted Gemini-assisted understanding result."""
    from app.db.models import Document

    service = LlmUnderstandingService(session)
    try:
        row = service.get_latest(document_id)
    except LlmUnderstandingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    document = session.get(Document, document_id)
    return _llm_to_response(
        row,
        document_status=document.status if document is not None else None,
    )
