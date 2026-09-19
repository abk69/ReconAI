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


class PolicyVersionStatus(StrEnum):
    """Lifecycle status for a policy knowledge-base version (M7.1)."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class ResolutionPlanStatus(StrEnum):
    """Lifecycle status for an agentic resolution plan (M8).

    Plans propose workflow actions only — they never mutate financial truth.
    """

    PROPOSED = "PROPOSED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ProposedActionStatus(StrEnum):
    """Lifecycle status for a single proposed resolution action."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ActionType(StrEnum):
    """Explicitly registered workflow actions (M8.1).

    Financial mutation actions (MODIFY_*, DELETE_*, APPROVE_PAYMENT) are
    intentionally absent and must never be added without a later milestone.
    """

    ROUTE_TO_REVIEW = "ROUTE_TO_REVIEW"
    REQUEST_VENDOR_CLARIFICATION = "REQUEST_VENDOR_CLARIFICATION"
    REQUEST_MISSING_DOCUMENT = "REQUEST_MISSING_DOCUMENT"
    ESCALATE_TO_MANAGER = "ESCALATE_TO_MANAGER"


class ApprovalDecision(StrEnum):
    """Human decision recorded on an ActionApproval row."""

    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ExecutionStatus(StrEnum):
    """Status of an ActionExecution attempt."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
