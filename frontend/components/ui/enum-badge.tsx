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
  EXTRACTION_FAILED: "danger",
  VALIDATION_FAILED: "danger",
};

export function EnumBadge({ value, kind }: { value: string; kind: "severity" | "status" }) {
  const tone =
    kind === "severity" ? (SEVERITY_TONE[value] ?? "neutral") : (STATUS_TONE[value] ?? "neutral");
  return (
    <span className="inline-flex items-center gap-2">
      <StatusBadge label={value} tone={tone} />
      <span className="text-xs text-ink-muted">{readableLabel(value)}</span>
    </span>
  );
}
