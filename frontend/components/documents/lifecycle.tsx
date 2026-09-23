import type { UnderstandingResult } from "@/types/documents";
import type { DocumentItem } from "@/types/procurement";
import type { ReviewTask } from "@/types/workflow";
import { formatTimestamp } from "@/lib/labels";

export type LifecycleStep = {
  label: string;
  state: "Reached" | "Current" | "Not reached";
  note: string;
};

export function buildLifecycle(
  document: DocumentItem,
  understanding: UnderstandingResult | null,
  review: ReviewTask | null,
): LifecycleStep[] {
  const status = document.status;
  const reviewStatus = review?.status ?? null;
  const promoted = Boolean(review?.promoted_entity_id);
  const extractionStored = understanding !== null && understanding.outcome !== "EXTRACTION_FAILED";

  const validatedState: LifecycleStep["state"] =
    status === "UPLOADED" ? "Not reached" : status === "VALIDATION_FAILED" ? "Current" : "Reached";

  let understandingState: LifecycleStep["state"] = "Not reached";
  if (status === "EXTRACTION_PENDING" || status === "EXTRACTING") {
    understandingState = "Current";
  } else if (understanding) {
    understandingState = "Reached";
  }

  let extractedState: LifecycleStep["state"] = "Not reached";
  if (status === "EXTRACTION_FAILED") {
    extractedState = "Current";
  } else if (status === "EXTRACTED" || status === "NORMALIZED") {
    extractedState = "Current";
  } else if (extractionStored || status === "REVIEW_REQUIRED" || status === "REVIEW_REJECTED" || status === "READY_FOR_RECONCILIATION") {
    extractedState = "Reached";
  }

  let reviewState: LifecycleStep["state"] = "Not reached";
  if (reviewStatus === "PENDING" || reviewStatus === "IN_REVIEW" || status === "REVIEW_REQUIRED") {
    reviewState = "Current";
  } else if (review || status === "REVIEW_REJECTED" || status === "READY_FOR_RECONCILIATION") {
    reviewState = "Reached";
  }

  let decisionState: LifecycleStep["state"] = "Not reached";
  if (reviewStatus === "REJECTED" || status === "REVIEW_REJECTED") {
    decisionState = "Current";
  } else if (reviewStatus === "APPROVED" || reviewStatus === "CORRECTED" || promoted) {
    decisionState = "Reached";
  }

  return [
    {
      label: "Intake",
      state: "Reached",
      note: `Stored upload time ${formatTimestamp(document.created_at)}.`,
    },
    {
      label: "Validated",
      state: validatedState,
      note:
        status === "VALIDATION_FAILED"
          ? "Stored document status is VALIDATION_FAILED."
          : status === "UPLOADED"
            ? "Stored document status is UPLOADED."
            : "Stored document status is no longer UPLOADED.",
    },
    {
      label: "Understanding",
      state: understandingState,
      note: understanding
        ? `Stored extraction outcome ${understanding.outcome}. Extractor ${understanding.extractor_version}.`
        : "No extraction result is stored for this document.",
    },
    {
      label: "Extracted",
      state: extractedState,
      note:
        status === "EXTRACTION_FAILED"
          ? "Stored document status is EXTRACTION_FAILED."
          : extractionStored
            ? "A stored extraction candidate exists. It is not an authoritative procurement record."
            : "No extraction candidate is stored.",
    },
    {
      label: "Review",
      state: reviewState,
      note: review
        ? `Stored review status ${review.status}. Created ${formatTimestamp(review.created_at)}.`
        : "No review task exists for this document.",
    },
    {
      label: "Approved or corrected",
      state: decisionState,
      note:
        reviewStatus === "APPROVED" || reviewStatus === "CORRECTED"
          ? `Stored review status ${reviewStatus}${
              review?.completed_at ? `. Completed ${formatTimestamp(review.completed_at)}` : ""
            }.`
          : reviewStatus === "REJECTED" || status === "REVIEW_REJECTED"
            ? "Stored review status is rejected."
            : "No approval or correction is stored.",
    },
    {
      label: "Promoted",
      state: promoted ? "Reached" : "Not reached",
      note: promoted
        ? `Stored promotion target ${review?.promoted_entity_type ?? "record"}${
            review?.promoted_at ? ` at ${formatTimestamp(review.promoted_at)}` : ""
          }.`
        : "No promotion is stored. An extraction candidate is not a promoted record.",
    },
    {
      label: "Ready for reconciliation",
      state: status === "READY_FOR_RECONCILIATION" ? "Current" : "Not reached",
      note:
        status === "READY_FOR_RECONCILIATION"
          ? "Stored document status is READY_FOR_RECONCILIATION."
          : "Stored document status is not READY_FOR_RECONCILIATION.",
    },
  ];
}

export function Lifecycle({ steps }: { steps: LifecycleStep[] }) {
  return (
    <section className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 className="text-base font-semibold text-ink">Derived workflow view</h2>
      <p className="mt-1 text-sm leading-6 text-ink-muted">
        Steps follow the stored document status and related records. A time is shown only when that
        record stores one. This view does not replace the current document status.
      </p>
      <ol className="mt-4 space-y-3">
        {steps.map((step) => (
          <li
            key={step.label}
            className="border-l-2 border-line pl-3"
            aria-current={step.state === "Current" ? "step" : undefined}
          >
            <p className="text-sm font-medium text-ink">
              {step.label}
              <span className="ml-2 text-xs font-normal tracking-wide text-ink-muted uppercase">
                {step.state}
              </span>
            </p>
            <p className="mt-1 text-sm leading-6 text-ink-muted">{step.note}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
