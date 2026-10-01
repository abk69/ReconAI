"""Document intake validation, hashing, storage, and metadata persistence."""

from __future__ import annotations

import contextlib
import hashlib
import re
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Document, GoodsReceipt, Invoice, PurchaseOrder, Vendor
from app.domain.enums import DocumentStatus, DocumentType, InvoiceStatus
from app.services.workspace_query import like_pattern
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


def summarize_related_invoices(invoices: list[Invoice]) -> str | None:
    """Order-independent summary of invoices that share one purchase order."""
    if not invoices:
        return None
    ordered = sorted(invoices, key=lambda invoice: invoice.invoice_number)
    matched = sum(1 for invoice in ordered if invoice.status == InvoiceStatus.MATCHED.value)
    problems = sum(1 for invoice in ordered if invoice.status == InvoiceStatus.EXCEPTION.value)
    pending = len(ordered) - matched - problems
    parts: list[str] = []
    if matched:
        parts.append("1 matched" if matched == 1 else f"{matched} matched")
    if problems:
        parts.append("1 with a problem" if problems == 1 else f"{problems} with problems")
    if pending:
        parts.append("1 not matched yet" if pending == 1 else f"{pending} not matched yet")
    noun = "invoice" if len(ordered) == 1 else "invoices"
    return f"{len(ordered)} related {noun} — {', '.join(parts)}"


def _ambiguity_summary(validation: object) -> str | None:
    if not isinstance(validation, dict):
        return None
    messages = [
        str(issue.get("message"))
        for issue in validation.get("issues") or []
        if isinstance(issue, dict)
        and issue.get("code") == "AMBIGUOUS_FIELD"
        and issue.get("message")
    ]
    return " ".join(messages) or None


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

    def list_page(
        self,
        *,
        document_type: DocumentType | None = None,
        status: DocumentStatus | None = None,
        vendor_id: UUID | None = None,
        purchase_order_id: UUID | None = None,
        invoice_id: UUID | None = None,
        goods_receipt_id: UUID | None = None,
        q: str | None = None,
        extraction_outcome: str | None = None,
        review_status: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> tuple[list[Document], int]:
        from app.db.models import DocumentExtractionResult, ReviewTask

        filters = []
        if document_type is not None:
            filters.append(Document.document_type == document_type.value)
        if status is not None:
            filters.append(Document.status == status.value)
        if vendor_id is not None:
            filters.append(Document.vendor_id == vendor_id)
        if purchase_order_id is not None:
            filters.append(Document.purchase_order_id == purchase_order_id)
        if invoice_id is not None:
            filters.append(Document.invoice_id == invoice_id)
        if goods_receipt_id is not None:
            filters.append(Document.goods_receipt_id == goods_receipt_id)
        if q:
            filters.append(Document.original_filename.ilike(like_pattern(q), escape="\\"))
        count_stmt = select(func.count(func.distinct(Document.id))).select_from(Document)
        stmt = select(Document)
        if extraction_outcome is not None:
            count_stmt = count_stmt.join(
                DocumentExtractionResult,
                DocumentExtractionResult.document_id == Document.id,
            )
            stmt = stmt.join(
                DocumentExtractionResult,
                DocumentExtractionResult.document_id == Document.id,
            )
            filters.append(DocumentExtractionResult.outcome == extraction_outcome)
        if review_status is not None:
            count_stmt = count_stmt.join(ReviewTask, ReviewTask.document_id == Document.id)
            stmt = stmt.join(ReviewTask, ReviewTask.document_id == Document.id)
            filters.append(ReviewTask.status == review_status)
        if filters:
            count_stmt = count_stmt.where(*filters)
        total = int(self._session.scalar(count_stmt) or 0)
        stmt = stmt.order_by(Document.created_at.desc()).distinct()
        if filters:
            stmt = stmt.where(*filters)
        if offset:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.scalars(stmt).all()), total

    def workspace_facts(self, document_ids: list[UUID]) -> dict[UUID, dict[str, str | None]]:
        """Latest stored extraction outcome, review status, and purchase-order readiness."""
        from app.db.models import DocumentExtractionResult, GoodsReceipt, PurchaseOrder, ReviewTask

        facts: dict[UUID, dict[str, str | None]] = {
            document_id: {
                "detected_type": None,
                "extraction_outcome": None,
                "review_status": None,
                "po_number": None,
                "purchase_order_ready": "false",
                "goods_receipt_ready": "false",
                "invoice_ready": "false",
                "invoice_number": None,
                "reconciliation_status": None,
                "related_invoice_summary": None,
                "ambiguity_summary": None,
            }
            for document_id in document_ids
        }
        if not document_ids:
            return facts
        extractions = self._session.scalars(
            select(DocumentExtractionResult).where(
                DocumentExtractionResult.document_id.in_(document_ids)
            )
        ).all()
        for row in extractions:
            facts[row.document_id]["detected_type"] = row.detected_type
            facts[row.document_id]["extraction_outcome"] = row.outcome
            candidate = row.candidate if isinstance(row.candidate, dict) else {}
            po_number = candidate.get("po_number")
            if isinstance(po_number, str) and po_number.strip():
                facts[row.document_id]["po_number"] = po_number.strip()
            facts[row.document_id]["ambiguity_summary"] = _ambiguity_summary(row.validation)
        reviews = self._session.scalars(
            select(ReviewTask)
            .where(ReviewTask.document_id.in_(document_ids))
            .order_by(ReviewTask.created_at.asc())
        ).all()
        for task in reviews:
            facts[task.document_id]["review_status"] = task.status
        numbers = {
            value
            for fact in facts.values()
            if isinstance((value := fact.get("po_number")), str) and value
        }
        order_ids: dict[str, UUID] = {}
        if numbers:
            orders = self._session.scalars(
                select(PurchaseOrder).where(PurchaseOrder.po_number.in_(numbers))
            ).all()
            order_ids = {order.po_number: order.id for order in orders}
        stored_rows = list(
            self._session.scalars(select(Document).where(Document.id.in_(document_ids))).all()
        )
        po_ids = set(order_ids.values())
        for row in stored_rows:
            if row.purchase_order_id is not None:
                po_ids.add(row.purchase_order_id)
                facts[row.id]["purchase_order_ready"] = "true"
            if row.goods_receipt_id is not None:
                facts[row.id]["goods_receipt_ready"] = "true"
        receipt_ids: set[object] = set()
        invoices_by_po: dict[UUID, list[Invoice]] = {}
        if po_ids:
            receipt_ids = set(
                self._session.scalars(
                    select(GoodsReceipt.purchase_order_id).where(
                        GoodsReceipt.purchase_order_id.in_(po_ids)
                    )
                ).all()
            )
            for invoice in self._session.scalars(
                select(Invoice).where(Invoice.purchase_order_id.in_(po_ids))
            ).all():
                if invoice.purchase_order_id is None:
                    continue
                invoices_by_po.setdefault(invoice.purchase_order_id, []).append(invoice)
        direct_ids = [row.invoice_id for row in stored_rows if row.invoice_id is not None]
        direct: dict[UUID, Invoice] = {}
        if direct_ids:
            linked_invoices = self._session.scalars(
                select(Invoice).where(Invoice.id.in_(direct_ids))
            ).all()
            for invoice in linked_invoices:
                direct[invoice.id] = invoice

        def apply_own_invoice(fact: dict[str, str | None], invoice: Invoice) -> None:
            fact["invoice_ready"] = "true"
            fact["invoice_number"] = invoice.invoice_number
            if invoice.status in {InvoiceStatus.MATCHED.value, InvoiceStatus.EXCEPTION.value}:
                fact["reconciliation_status"] = invoice.status
            else:
                fact["reconciliation_status"] = None

        for fact in facts.values():
            order_id = order_ids.get(fact.get("po_number") or "")
            if order_id is None:
                continue
            fact["purchase_order_ready"] = "true"
            if order_id in receipt_ids:
                fact["goods_receipt_ready"] = "true"
        for row in stored_rows:
            fact = facts[row.id]
            if row.purchase_order_id is not None and row.purchase_order_id in receipt_ids:
                fact["goods_receipt_ready"] = "true"
            if row.invoice_id is not None and row.invoice_id in direct:
                apply_own_invoice(fact, direct[row.invoice_id])
                continue
            kind = fact.get("detected_type") or row.document_type
            if kind not in {DocumentType.PO.value, DocumentType.GRN.value}:
                continue
            order_id = row.purchase_order_id or order_ids.get(fact.get("po_number") or "")
            related = invoices_by_po.get(order_id, []) if order_id is not None else []
            summary = summarize_related_invoices(related)
            if summary is None:
                continue
            fact["related_invoice_summary"] = summary
            fact["invoice_ready"] = "true"
            fact["reconciliation_status"] = None
        return facts

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
        rows, _total = self.list_page(
            document_type=document_type,
            status=status,
            vendor_id=vendor_id,
            purchase_order_id=purchase_order_id,
            invoice_id=invoice_id,
            goods_receipt_id=goods_receipt_id,
        )
        return rows

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
