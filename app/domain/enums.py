"""Domain enumerations for procurement documents and exceptions."""

from enum import StrEnum


class DocumentType(StrEnum):
    """Types of procurement documents ingested by ReconAI."""

    PO = "PO"
    GRN = "GRN"
    INVOICE = "INVOICE"
    UNKNOWN = "UNKNOWN"


class DocumentStatus(StrEnum):
    """Lifecycle status for an ingested file document.

    M3 performs intake only. A successfully validated upload becomes
    ``VALIDATED``. Extraction states are reserved for M4+.
    """

    UPLOADED = "UPLOADED"
    VALIDATED = "VALIDATED"
    EXTRACTION_PENDING = "EXTRACTION_PENDING"
    EXTRACTING = "EXTRACTING"
    EXTRACTED = "EXTRACTED"
    NORMALIZED = "NORMALIZED"
    READY_FOR_RECONCILIATION = "READY_FOR_RECONCILIATION"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    VALIDATION_FAILED = "VALIDATION_FAILED"


class ExceptionType(StrEnum):
    """Classifications of reconciliation exceptions."""

    QUANTITY_MISMATCH = "QUANTITY_MISMATCH"
    PRICE_MISMATCH = "PRICE_MISMATCH"
    TAX_MISMATCH = "TAX_MISMATCH"
    IDENTIFIER_MISMATCH = "IDENTIFIER_MISMATCH"
    DUPLICATE_INVOICE = "DUPLICATE_INVOICE"
    DATE_MISMATCH = "DATE_MISMATCH"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    OTHER = "OTHER"


class ExceptionSeverity(StrEnum):
    """Severity levels for reconciliation exceptions."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class PurchaseOrderStatus(StrEnum):
    """Lifecycle status for a purchase order."""

    DRAFT = "DRAFT"
    OPEN = "OPEN"
    PARTIALLY_RECEIVED = "PARTIALLY_RECEIVED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class GoodsReceiptStatus(StrEnum):
    """Lifecycle status for a goods receipt / GRN."""

    DRAFT = "DRAFT"
    POSTED = "POSTED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(StrEnum):
    """Lifecycle status for a vendor invoice."""

    DRAFT = "DRAFT"
    RECEIVED = "RECEIVED"
    MATCHED = "MATCHED"
    EXCEPTION = "EXCEPTION"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"


class ExceptionStatus(StrEnum):
    """Workflow status for a reconciliation exception."""

    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    RESOLVED = "RESOLVED"
    DISMISSED = "DISMISSED"


class ReconciliationStatus(StrEnum):
    """Outcome of a deterministic reconciliation run."""

    MATCHED = "MATCHED"
    EXCEPTIONS_FOUND = "EXCEPTIONS_FOUND"
    INCOMPLETE = "INCOMPLETE"
