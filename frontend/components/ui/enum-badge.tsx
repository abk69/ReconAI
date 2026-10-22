import type { SignalTone } from "@/types/domain";

import { StatusBadge } from "@/components/ui/status-badge";
import { readableLabel } from "@/lib/labels";

const SEVERITY_TONE: Record<string, SignalTone> = {
  LOW: "success",
  MEDIUM: "warning",
  HIGH: "danger",
  CRITICAL: "danger",
};

const STATUS_TONE: Record<string, SignalTone> = {
  OPEN: "warning",
  IN_REVIEW: "info",
  RESOLVED: "success",
  DISMISSED: "neutral",
  PENDING: "warning",
  APPROVED: "success",
  CORRECTED: "info",
  REJECTED: "danger",
  REVIEW_REQUIRED: "warning",
  REVIEW_REJECTED: "danger",
  READY_FOR_RECONCILIATION: "success",
  VALIDATED: "info",
  UPLOADED: "neutral",
  EXTRACTED: "info",
  NORMALIZED: "info",
  EXTRACTING: "info",
  EXTRACTION_PENDING: "info",
  DRAFT: "neutral",
  ACTIVE: "success",
  RETIRED: "neutral",
  POSTED: "success",
  CLOSED: "success",
  CANCELLED: "neutral",
  RECEIVED: "info",
  MATCHED: "success",
  EXCEPTION: "danger",
  EXCEPTIONS_FOUND: "danger",
  INCOMPLETE: "warning",
  PARTIALLY_RECEIVED: "warning",
  EXTRACTION_FAILED: "danger",
  VALIDATION_FAILED: "danger",
  PROPOSED: "info",
  APPROVAL_REQUIRED: "warning",
  EXECUTING: "info",
  COMPLETED: "success",
  FAILED: "danger",
  NO_ACTION_RECOMMENDED: "neutral",
  SUPPORTED: "info",
  INSUFFICIENT_EVIDENCE: "warning",
  CONFLICTING_POLICY: "danger",
  PROVIDER_ERROR: "danger",
  SUCCEEDED: "success",
  RUNNING: "info",
};

export function EnumBadge({ value, kind }: { value: string; kind: "severity" | "status" }) {
  const tone =
    kind === "severity" ? (SEVERITY_TONE[value] ?? "neutral") : (STATUS_TONE[value] ?? "neutral");
  const label = readableLabel(value);
  return (
    <span className="inline-flex items-center" title={value === label ? undefined : value}>
      <StatusBadge label={label} tone={tone} />
    </span>
  );
}
