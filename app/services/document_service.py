"""Document intake validation, hashing, storage, and metadata persistence."""

from __future__ import annotations

import contextlib
import hashlib
import re
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, GoodsReceipt, Invoice, PurchaseOrder, Vendor
from app.domain.enums import DocumentStatus, DocumentType
from app.storage.base import StorageBackend, StorageError
from app.storage.local import LocalFileStorage

ALLOWED_EXTENSIONS: dict[str, set[str]] = {
    ".pdf": {"application/pdf"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".png": {"image/png"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    },
}

_UNSAFE_FILENAME = re.compile(r"[\\/]|(\.\.)")


class DocumentServiceError(Exception):
    """Base document service error."""


class DocumentValidationError(DocumentServiceError):
    """Raised when upload validation fails."""


class DocumentNotFoundError(DocumentServiceError):
    """Raised when a document metadata row is missing."""


class DocumentAssociationError(DocumentServiceError):
    """Raised when an association FK does not exist."""


def sanitize_original_filename(filename: str | None) -> str:
    """Preserve a display name only; strip path components and traversal sequences."""
    raw = (filename or "upload").strip() or "upload"
    name = Path(raw.replace("\\", "/")).name
    name = _UNSAFE_FILENAME.sub("_", name)
    return name[:512] or "upload"


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_upload(
    *,
    original_filename: str,
    content_type: str | None,
    data: bytes,
    max_upload_bytes: int,
) -> tuple[str, str, str]:
    """Validate size, extension, and MIME. Return (safe_name, extension, mime)."""
    if not data:
        raise DocumentValidationError("Uploaded file is empty.")
    if len(data) > max_upload_bytes:
        raise DocumentValidationError(f"File exceeds maximum size of {max_upload_bytes} bytes.")

    safe_name = sanitize_original_filename(original_filename)
    extension = Path(safe_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise DocumentValidationError(f"Unsupported file extension '{extension or '(none)'}'.")

    mime = (content_type or "").split(";")[0].strip().lower()
    allowed_mimes = ALLOWED_EXTENSIONS[extension]
    if mime not in allowed_mimes:
        raise DocumentValidationError(
            f"Unsupported MIME type '{mime or '(none)'}' for extension '{extension}'."
        )
    return safe_name, extension, mime


class DocumentService:
    """Secure document intake service (no OCR / extraction)."""

    def __init__(
        self,
        session: Session,
        storage: StorageBackend | None = None,
    ) -> None:
        self._session = session
        settings = get_settings()
        self._max_upload_bytes = settings.max_upload_bytes
        self._storage = storage or LocalFileStorage(settings.storage_root)

    def _assert_association_targets(
        self,
        *,
        vendor_id: UUID | None,
        purchase_order_id: UUID | None,
        goods_receipt_id: UUID | None,
        invoice_id: UUID | None,
    ) -> None:
        if vendor_id is not None and self._session.get(Vendor, vendor_id) is None:
            raise DocumentAssociationError(f"Vendor {vendor_id} was not found.")
        if (
            purchase_order_id is not None
            and self._session.get(PurchaseOrder, purchase_order_id) is None
        ):
            raise DocumentAssociationError(f"Purchase order {purchase_order_id} was not found.")
        if (
            goods_receipt_id is not None
            and self._session.get(GoodsReceipt, goods_receipt_id) is None
        ):
            raise DocumentAssociationError(f"Goods receipt {goods_receipt_id} was not found.")
        if invoice_id is not None and self._session.get(Invoice, invoice_id) is None:
            raise DocumentAssociationError(f"Invoice {invoice_id} was not found.")

    def upload(
        self,
        *,
        filename: str | None,
        content_type: str | None,
        data: bytes,
        document_type: DocumentType | None = None,
        vendor_id: UUID | None = None,
        purchase_order_id: UUID | None = None,
        goods_receipt_id: UUID | None = None,
        invoice_id: UUID | None = None,
    ) -> tuple[Document, bool]:
        """Validate, hash, store, and persist metadata.

        Returns ``(document, is_duplicate)``. Exact content duplicates return the
        existing metadata row without creating another storage object.
        """
        try:
            safe_name, extension, mime = validate_upload(
                original_filename=filename or "upload",
                content_type=content_type,
                data=data,
                max_upload_bytes=self._max_upload_bytes,
            )
        except DocumentValidationError:
            raise

        self._assert_association_targets(
            vendor_id=vendor_id,
            purchase_order_id=purchase_order_id,
            goods_receipt_id=goods_receipt_id,
            invoice_id=invoice_id,
        )

        digest = compute_sha256(data)
        existing = self._session.scalar(select(Document).where(Document.sha256 == digest))
        if existing is not None:
            return existing, True

        document_id = uuid4()
        try:
            stored_filename, absolute_path = self._storage.save(
                document_id=document_id,
                extension=extension,
                data=data,
            )
        except StorageError as exc:
            raise DocumentServiceError(str(exc)) from exc

        # Relative path under storage root for portability in metadata.
        storage_path = str(Path(stored_filename))

        row = Document(
            id=document_id,
            original_filename=safe_name,
            stored_filename=stored_filename,
            document_type=(document_type or DocumentType.UNKNOWN).value,
            mime_type=mime,
            file_extension=extension,
            file_size=len(data),
            sha256=digest,
            storage_path=storage_path,
            status=DocumentStatus.VALIDATED.value,
            vendor_id=vendor_id,
            purchase_order_id=purchase_order_id,
            goods_receipt_id=goods_receipt_id,
            invoice_id=invoice_id,
        )
        self._session.add(row)
        try:
            self._session.commit()
        except Exception:
            self._session.rollback()
            with contextlib.suppress(StorageError):
                self._storage.delete(stored_filename=stored_filename)
            raise

        # absolute_path kept only for local verification; metadata uses storage_path.
        _ = absolute_path
        return row, False

    def get(self, document_id: UUID) -> Document:
        row = self._session.get(Document, document_id)
        if row is None:
            raise DocumentNotFoundError(f"Document {document_id} was not found.")
        return row

    def list(
        self,
        *,
        document_type: DocumentType | None = None,
        status: DocumentStatus | None = None,
        vendor_id: UUID | None = None,
        purchase_order_id: UUID | None = None,
        invoice_id: UUID | None = None,
        goods_receipt_id: UUID | None = None,
    ) -> list[Document]:
        stmt = select(Document).order_by(Document.created_at.desc())
        if document_type is not None:
            stmt = stmt.where(Document.document_type == document_type.value)
        if status is not None:
            stmt = stmt.where(Document.status == status.value)
        if vendor_id is not None:
            stmt = stmt.where(Document.vendor_id == vendor_id)
        if purchase_order_id is not None:
            stmt = stmt.where(Document.purchase_order_id == purchase_order_id)
        if invoice_id is not None:
            stmt = stmt.where(Document.invoice_id == invoice_id)
        if goods_receipt_id is not None:
            stmt = stmt.where(Document.goods_receipt_id == goods_receipt_id)
        return list(self._session.scalars(stmt).all())

    def update_associations(
        self,
        document_id: UUID,
        *,
        document_type: DocumentType | None = None,
        vendor_id: UUID | None = None,
        purchase_order_id: UUID | None = None,
        goods_receipt_id: UUID | None = None,
        invoice_id: UUID | None = None,
        set_vendor: bool = False,
        set_purchase_order: bool = False,
        set_goods_receipt: bool = False,
        set_invoice: bool = False,
    ) -> Document:
        """Update document type / associations. Explicit set_* flags allow clearing to null."""
        row = self.get(document_id)
        next_vendor = vendor_id if set_vendor else row.vendor_id
        next_po = purchase_order_id if set_purchase_order else row.purchase_order_id
        next_grn = goods_receipt_id if set_goods_receipt else row.goods_receipt_id
        next_invoice = invoice_id if set_invoice else row.invoice_id
        self._assert_association_targets(
            vendor_id=next_vendor,
            purchase_order_id=next_po,
            goods_receipt_id=next_grn,
            invoice_id=next_invoice,
        )
        if document_type is not None:
            row.document_type = document_type.value
        if set_vendor:
            row.vendor_id = vendor_id
        if set_purchase_order:
            row.purchase_order_id = purchase_order_id
        if set_goods_receipt:
            row.goods_receipt_id = goods_receipt_id
        if set_invoice:
            row.invoice_id = invoice_id
        self._session.commit()
        return row
