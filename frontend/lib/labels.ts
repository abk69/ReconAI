const LABELS: Record<string, string> = {
  PRICE_MISMATCH: "Price mismatch",
  QUANTITY_MISMATCH: "Quantity mismatch",
  TAX_MISMATCH: "Tax mismatch",
  IDENTIFIER_MISMATCH: "Identifier mismatch",
  DUPLICATE_INVOICE: "Duplicate invoice",
  DATE_MISMATCH: "Date mismatch",
  MISSING_DOCUMENT: "Missing document",
  OTHER: "Other",
  OPEN: "Open",
  IN_REVIEW: "In review",
  RESOLVED: "Resolved",
  DISMISSED: "Dismissed",
  PENDING: "Pending",
  APPROVED: "Approved",
  CORRECTED: "Corrected",
  REJECTED: "Rejected",
  UPLOADED: "Uploaded",
  VALIDATED: "Validated",
  EXTRACTION_PENDING: "Extraction pending",
  EXTRACTING: "Extracting",
  EXTRACTED: "Extracted",
  NORMALIZED: "Normalized",
  READY_FOR_RECONCILIATION: "Ready for reconciliation",
  EXTRACTION_FAILED: "Extraction failed",
  VALIDATION_FAILED: "Validation failed",
  REVIEW_REQUIRED: "Review required",
  REVIEW_REJECTED: "Review rejected",
  document_recorded: "Document recorded",
  reconciliation_exception: "Reconciliation exception",
  review_decision: "Review decision",
  anomaly_signal: "Anomaly signal",
  risk_profile: "Risk profile",
  resolution_audit: "Resolution audit",
  LOW: "Low",
  MEDIUM: "Medium",
  HIGH: "High",
  CRITICAL: "Critical",
  VENDOR: "Vendor",
  INVOICE: "Invoice",
  PURCHASE_ORDER: "Purchase order",
};

/** Readable label. The original backend value is still shown beside it. */
export function readableLabel(value: string): string {
  return LABELS[value] ?? value.replaceAll("_", " ");
}

export function formatTimestamp(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
