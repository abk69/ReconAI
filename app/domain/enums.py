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
    ``VALIDATED``. M4 advances extraction states; ambiguous results use
    ``REVIEW_REQUIRED``. M5 promotes approved candidates to
    ``READY_FOR_RECONCILIATION`` or marks rejects as ``REVIEW_REJECTED``.
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
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_REJECTED = "REVIEW_REJECTED"


class FieldConfidence(StrEnum):
    """Deterministic, rule-based confidence for extracted fields (not ML)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ExtractionOutcome(StrEnum):
    """Outcome of a document-understanding run (separate from DocumentStatus)."""

    READY_FOR_RECONCILIATION = "READY_FOR_RECONCILIATION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


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


class ReviewStatus(StrEnum):
    """Lifecycle status for a human review task (M5)."""

    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    CORRECTED = "CORRECTED"
    REJECTED = "REJECTED"


class ReviewAction(StrEnum):
    """Field-level or task-level reviewer action."""

    APPROVE = "APPROVE"
    CORRECT = "CORRECT"
    REJECT = "REJECT"


class ReviewPriority(StrEnum):
    """Priority for review queue ordering."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ApplicationQuality(StrEnum):
    """Application-computed quality for an LLM-assisted extraction (not model self-score)."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class LlmInvocationStatus(StrEnum):
    """Whether Gemini was invoked for a document understanding run."""

    SKIPPED_M4_SUFFICIENT = "SKIPPED_M4_SUFFICIENT"
    INVOKED = "INVOKED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    EVIDENCE_FAILED = "EVIDENCE_FAILED"
    DISAGREEMENT = "DISAGREEMENT"
