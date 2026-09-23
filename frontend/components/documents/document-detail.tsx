"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { Lifecycle, buildLifecycle } from "@/components/documents/lifecycle";
import { RecordState } from "@/components/procurement/record-state";
import { resourceError, useResource } from "@/components/procurement/use-resource";
import { DataTable } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { getLlmUnderstanding, getRawExtraction, getUnderstanding } from "@/lib/api/documents";
import { isApiError } from "@/lib/api/errors";
import { getDocument, getVendor, listExceptions } from "@/lib/api/procurement";
import { listReviewTasks } from "@/lib/api/workflow";
import { formatTimestamp } from "@/lib/labels";
import type {
  FieldDiff,
  FieldEvidence,
  LlmUnderstanding,
  UnderstandingResult,
  ValidationResult,
} from "@/types/documents";
import type { DocumentItem, ExceptionList, Vendor } from "@/types/procurement";
import type { ReviewTask } from "@/types/workflow";

type Bundle = {
  document: DocumentItem;
  understanding: UnderstandingResult | null;
  llm: LlmUnderstanding | null;
  review: ReviewTask | null;
  vendor: Vendor | null;
  exceptions: ExceptionList | null;
};

function isScalar(value: unknown): value is string | number | boolean | null {
  return value === null || ["string", "number", "boolean"].includes(typeof value);
}

async function optional<T>(request: Promise<T>): Promise<T | null> {
  try {
    return await request;
  } catch (error) {
    if (isApiError(error) && error.status === 404) return null;
    throw error;
  }
}

function Section({
  title,
  kicker,
  children,
}: {
  title: string;
  kicker?: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-md border border-line bg-surface p-5 shadow-card">
      {kicker ? <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">{kicker}</p> : null}
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-6">{children}</div>
    </section>
  );
}

function RawBlock({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="rounded-md border border-line bg-canvas">
      <summary className="cursor-pointer px-3 py-2 text-sm text-brand">{title}</summary>
      <pre className="max-h-80 overflow-auto p-3 text-xs text-ink">{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}

function CandidateFields({ candidate, heading }: { candidate: Record<string, unknown> | null; heading: string }) {
  if (!candidate) {
    return <p>No candidate was stored.</p>;
  }
  const scalars = Object.entries(candidate).filter(([key, value]) => key !== "lines" && key !== "evidence" && isScalar(value));
  const lines = Array.isArray(candidate.lines) ? candidate.lines.filter((line) => line && typeof line === "object") : [];
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-semibold text-ink">{heading}</h3>
      {scalars.length === 0 ? <p className="text-ink-muted">No scalar candidate fields were stored.</p> : (
        <dl className="grid gap-3 sm:grid-cols-2">
          {scalars.map(([key, value]) => (
            <div key={key}>
              <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">{key}</dt>
              <dd className="mt-1 break-words">{value === null ? "null" : String(value)}</dd>
            </div>
          ))}
        </dl>
      )}
      {lines.length > 0 ? (
        <div className="overflow-x-auto">
          <DataTable
            caption="Candidate lines"
            rowKey={(row) => `${String(row.line_number ?? "line")}-${String(row.description ?? "")}`}
            rows={lines as Record<string, unknown>[]}
            columns={[
              { key: "n", header: "Line", cell: (row) => String(row.line_number ?? "—") },
              { key: "d", header: "Description", cell: (row) => String(row.description ?? "—") },
              { key: "q", header: "Quantity", cell: (row) => String(row.quantity ?? "—") },
              { key: "p", header: "Unit price", cell: (row) => String(row.unit_price ?? "—") },
              { key: "t", header: "Tax rate", cell: (row) => String(row.tax_rate ?? "—") },
            ]}
          />
        </div>
      ) : null}
    </div>
  );
}

function EvidenceList({ items, empty }: { items: FieldEvidence[]; empty: string }) {
  if (items.length === 0) {
    return <p className="text-ink-muted">{empty}</p>;
  }
  return (
    <ul className="space-y-3">
      {items.map((item, index) => (
        <li key={`${item.field_name ?? "field"}-${index}`} className="rounded-md border border-line p-3">
          <p className="font-medium">{item.field_name ?? "Field"}</p>
          <p>Stored value: {item.value === undefined || item.value === null ? "unavailable" : String(item.value)}</p>
          <p>Page: {item.page === null || item.page === undefined ? "unavailable" : item.page}</p>
          <p>Source: {item.source_type ?? item.sheet ?? item.cell ?? "unavailable"}</p>
          {item.sheet ? <p>Sheet: {item.sheet}</p> : null}
          {item.cell ? <p>Cell: {item.cell}</p> : null}
          <p>Snippet: {item.source_text || item.snippet || "unavailable"}</p>
          {item.extraction_method ? <p>Method: {item.extraction_method}</p> : null}
          {item.confidence ? <p>Stored field confidence: {item.confidence}</p> : null}
          {item.reason ? <p>{item.reason}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function ValidationBlock({ validation }: { validation: ValidationResult | null | undefined }) {
  const issues = validation?.issues ?? [];
  return (
    <div className="space-y-2">
      <p>Valid: {validation?.is_valid === undefined ? "unavailable" : validation.is_valid ? "yes" : "no"}</p>
      <p>Requires review: {validation?.requires_review === undefined ? "unavailable" : validation.requires_review ? "yes" : "no"}</p>
      {issues.length === 0 ? <p className="text-ink-muted">No validation issues were stored.</p> : (
        <ul className="space-y-2">
          {issues.map((issue, index) => (
            <li key={`${issue.code ?? "issue"}-${index}`}>
              {issue.severity === "error" ? "Issue" : issue.severity ?? "Issue"}: {issue.message ?? issue.code ?? "Stored validation issue"}
              {issue.field_name ? ` (${issue.field_name})` : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function DiffTable({ title, rows }: { title: string; rows: FieldDiff[] }) {
  if (rows.length === 0) return null;
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      <div className="overflow-x-auto">
        <DataTable
          caption={title}
          rowKey={(row) => `${row.field_path ?? "field"}-${row.status ?? ""}-${String(row.m4_value ?? "")}`}
          rows={rows}
          columns={[
            { key: "field", header: "Field", cell: (row) => row.field_path ?? "—" },
            { key: "m4", header: "M4 candidate", cell: (row) => String(row.m4_value ?? "—") },
            { key: "m6", header: "AI-assisted candidate", cell: (row) => String(row.gemini_value ?? "—") },
            { key: "status", header: "Stored status", cell: (row) => row.status ?? "—" },
          ]}
        />
      </div>
    </div>
  );
}

function promotedHref(entityType: string, entityId: string): string | null {
  if (entityType === "INVOICE") return `/invoices/${entityId}`;
  if (entityType === "PO") return `/purchase-orders/${entityId}`;
  if (entityType === "GRN") return `/goods-receipts/${entityId}`;
  return null;
}

function RawExtraction({ documentId }: { documentId: string }) {
  const [state, setState] = useState<{ kind: "idle" | "loading" | "ready" | "error"; text: string; value?: unknown }>({
    kind: "idle",
    text: "",
  });

  return (
    <details
      className="rounded-md border border-line bg-canvas"
      onToggle={(event) => {
        if (!event.currentTarget.open || state.kind !== "idle") return;
        setState({ kind: "loading", text: "Loading stored raw extraction." });
        getRawExtraction(documentId)
          .then((payload) => setState({ kind: "ready", text: "", value: payload.raw_extraction }))
          .catch((error: unknown) => setState({ kind: "error", text: resourceError(error, "Raw extraction") }));
      }}
    >
      <summary className="cursor-pointer px-3 py-2 text-sm text-brand">Raw extraction</summary>
      {state.kind === "loading" ? <p className="px-3 pb-3 text-sm">Loading stored raw extraction.</p> : null}
      {state.kind === "error" ? <p className="px-3 pb-3 text-sm">{state.text}</p> : null}
      {state.kind === "ready" ? (
        <pre className="max-h-80 overflow-auto p-3 text-xs text-ink">{JSON.stringify(state.value, null, 2)}</pre>
      ) : null}
    </details>
  );
}

function needsReview(document: DocumentItem, review: ReviewTask | null): boolean {
  return document.status === "REVIEW_REQUIRED" || review?.status === "PENDING" || review?.status === "IN_REVIEW";
}

export function DocumentIntelligencePage({ id }: { id: string }) {
  const state = useResource(
    id,
    async (signal) => {
      const document = await getDocument(id, signal);
      const [understanding, llm, reviews, vendor] = await Promise.all([
        optional(getUnderstanding(id, signal)),
        optional(getLlmUnderstanding(id, signal)),
        listReviewTasks({ document_id: id, limit: 5 }, signal),
        document.vendor_id ? optional(getVendor(document.vendor_id, signal)) : Promise.resolve(null),
      ]);
      const linkedId = document.invoice_id
        ? { invoice_id: document.invoice_id }
        : document.purchase_order_id
          ? { purchase_order_id: document.purchase_order_id }
          : document.goods_receipt_id
            ? { goods_receipt_id: document.goods_receipt_id }
            : null;
      const exceptions = linkedId ? await listExceptions({ ...linkedId, limit: 10 }, signal) : null;
      return {
        document,
        understanding,
        llm,
        review: reviews.items[0] ?? null,
        vendor,
        exceptions,
      } satisfies Bundle;
    },
    "Document",
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <RecordState state={state} loadingTitle="Loading document" empty={null}>
        {(bundle) => {
          const { document, understanding, llm, review, vendor, exceptions } = bundle;
          const steps = buildLifecycle(document, understanding, review);
          const promotedLink = review?.promoted_entity_id && review.promoted_entity_type
            ? promotedHref(review.promoted_entity_type, review.promoted_entity_id)
            : null;
          return (
            <>
              <div>
                <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Document intelligence</p>
                <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink">{document.original_filename}</h1>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
                  An extraction candidate is not authoritative procurement data. A promoted record is
                  created only after human review.
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <EnumBadge value={document.document_type} kind="status" />
                  <EnumBadge value={document.status} kind="status" />
                </div>
                <p className="mt-3 text-sm text-ink">Current document status: {document.status}</p>
              </div>

              {needsReview(document, review) && review ? (
                <section className="rounded-md border border-line bg-surface p-5 shadow-card">
                  <h2 className="text-base font-semibold text-ink">Human review required</h2>
                  <p className="mt-2 text-sm leading-6 text-ink-muted">
                    Stored review status {review.status}. Consequential review actions stay in the review center.
                  </p>
                  <Link className="mt-3 inline-block text-sm text-brand underline" href={`/review/${review.id}`}>
                    Open review
                  </Link>
                </section>
              ) : null}

              <dl className="grid gap-4 rounded-md border border-line bg-surface p-5 sm:grid-cols-2">
                <div>
                  <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Document id</dt>
                  <dd className="mt-1 break-all text-sm">{document.id}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Uploaded</dt>
                  <dd className="mt-1 text-sm">{formatTimestamp(document.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Updated</dt>
                  <dd className="mt-1 text-sm">{formatTimestamp(document.updated_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Detected type</dt>
                  <dd className="mt-1 text-sm">{understanding?.detected_type ?? "No extraction result is stored."}</dd>
                </div>
              </dl>

              <Lifecycle steps={steps} />

              <Section title="Original document" kicker="1">
                <dl className="grid gap-3 sm:grid-cols-2">
                  <div>
                    <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Filename</dt>
                    <dd className="mt-1 break-words">{document.original_filename}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">MIME type</dt>
                    <dd className="mt-1">{document.mime_type}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Extension</dt>
                    <dd className="mt-1">{document.file_extension}</dd>
                  </div>
                  <div>
                    <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Size</dt>
                    <dd className="mt-1">{document.file_size} bytes</dd>
                  </div>
                  <div className="sm:col-span-2">
                    <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">SHA-256</dt>
                    <dd className="mt-1 break-all">{document.sha256}</dd>
                  </div>
                </dl>
                <p className="text-ink-muted">A stored file is associated with this document. Preview is not available from this page.</p>
              </Section>

              <Section title="Extraction candidate" kicker="2">
                {understanding ? (
                  <>
                    <p>Extraction outcome: {understanding.outcome}</p>
                    <p>Extractor version: {understanding.extractor_version}</p>
                    {understanding.message ? <p>{understanding.message}</p> : null}
                    <CandidateFields candidate={understanding.candidate} heading="Deterministic extraction candidate" />
                    <RawBlock title="Raw candidate" value={understanding.candidate} />
                    {understanding.has_raw_extraction ? <RawExtraction documentId={document.id} /> : <p>No raw extraction was stored.</p>}
                  </>
                ) : (
                  <p>No extraction result is stored for this document.</p>
                )}
              </Section>

              <Section title="Validation" kicker="3">
                <p className="text-ink-muted">Validation findings are the stored deterministic results. This page does not add rules.</p>
                {understanding ? <ValidationBlock validation={understanding.validation} /> : <p>No validation result is stored.</p>}
                {understanding ? <RawBlock title="Validation payload" value={understanding.validation} /> : null}
              </Section>

              <Section title="Provenance" kicker="Evidence">
                <EvidenceList
                  items={understanding?.evidence ?? []}
                  empty={understanding ? "No field evidence was stored." : "Provenance is unavailable because no extraction result is stored."}
                />
                {understanding ? <RawBlock title="Evidence payload" value={understanding.evidence} /> : null}
              </Section>

              <Section title="Human review" kicker="4">
                {review ? (
                  <>
                    <p>Stored review status: {review.status}</p>
                    <p>Reviewer: {review.assigned_to ?? "No reviewer is stored."}</p>
                    <p>Created {formatTimestamp(review.created_at)}</p>
                    {review.reason ? <p>Reason: {review.reason}</p> : null}
                    {review.decisions.length === 0 ? <p>No decisions are stored.</p> : (
                      <div className="overflow-x-auto">
                        <DataTable
                          caption="Review decisions"
                          rowKey={(row) => row.id}
                          rows={review.decisions}
                          columns={[
                            { key: "action", header: "Action", cell: (row) => row.action },
                            { key: "reviewer", header: "Reviewer", cell: (row) => row.reviewer ?? "—" },
                            { key: "when", header: "Time", cell: (row) => formatTimestamp(row.created_at) },
                            { key: "reason", header: "Reason", cell: (row) => row.reason ?? "—" },
                          ]}
                        />
                      </div>
                    )}
                    <Link className="text-brand underline" href={`/review/${review.id}`}>Open review</Link>
                  </>
                ) : (
                  <p>No review task exists for this document.</p>
                )}
              </Section>

              <Section title="Promoted authoritative record" kicker="5">
                {review?.promoted_entity_id ? (
                  <>
                    <p>
                      Promoted {review.promoted_entity_type ?? "record"}
                      {review.promoted_at ? ` at ${formatTimestamp(review.promoted_at)}` : ""}.
                    </p>
                    {promotedLink ? (
                      <Link className="text-brand underline" href={promotedLink}>
                        Open promoted {review.promoted_entity_type} record
                      </Link>
                    ) : (
                      <p>Stored promotion id {review.promoted_entity_id}. No workspace route matches this entity type.</p>
                    )}
                  </>
                ) : (
                  <p>No promotion is stored yet. The extraction candidate remains untrusted.</p>
                )}
              </Section>

              <Section title="Gemini-assisted extraction" kicker="AI-assisted extraction">
                {llm ? (
                  <>
                    <p>This stored result is AI-assisted extraction. It is not authoritative procurement data.</p>
                    <p>Provider: {llm.provider}</p>
                    <p>Model: {llm.model}</p>
                    <p>Prompt version: {llm.prompt_version}</p>
                    <p>Invocation status: {llm.invocation_status}</p>
                    <p>Application quality: {llm.application_quality ?? "No application quality value was stored."}</p>
                    {llm.quality_reasons.length > 0 ? (
                      <ul className="list-disc pl-5">
                        {llm.quality_reasons.map((reason, index) => (
                          <li key={`${reason}-${index}`}>{reason}</li>
                        ))}
                      </ul>
                    ) : <p>No quality reasons were stored.</p>}
                    {llm.gate_reasons.length > 0 ? (
                      <div>
                        <h3 className="font-semibold">Quality gate reasons</h3>
                        <ul className="list-disc pl-5">
                          {llm.gate_reasons.map((reason, index) => (
                            <li key={`${reason}-${index}`}>{reason}</li>
                          ))}
                        </ul>
                      </div>
                    ) : <p>No quality-gate reasons were stored.</p>}
                    {llm.message ? <p>{llm.message}</p> : null}
                    {llm.error_message ? <p>Stored error: {llm.error_code ?? "error"}. {llm.error_message}</p> : null}
                    <p>Stored {formatTimestamp(llm.created_at)}</p>
                    {llm.usage ? (
                      <p>
                        Usage tokens: input {llm.usage.input_tokens ?? "unavailable"}, output {llm.usage.output_tokens ?? "unavailable"}, total {llm.usage.total_tokens ?? "unavailable"}.
                      </p>
                    ) : <p>No usage figures were stored.</p>}
                    <CandidateFields candidate={llm.candidate} heading="AI-assisted extraction candidate" />
                    <h3 className="font-semibold">Deterministic extraction vs AI-assisted extraction</h3>
                    {llm.comparison ? (
                      <>
                        <p>Stored comparison only. Disagreement is shown as stored. Neither candidate is marked correct here.</p>
                        {(llm.comparison.agreements ?? []).length > 0 ? (
                          <p>Stored agreements: {llm.comparison.agreements?.join(", ")}</p>
                        ) : <p>No stored agreements.</p>}
                        <DiffTable title="Stored disagreements" rows={llm.comparison.disagreements ?? []} />
                        <DiffTable title="Stored M4-only fields" rows={llm.comparison.m4_only ?? []} />
                        <DiffTable title="Stored AI-only fields" rows={llm.comparison.gemini_only ?? []} />
                        {(llm.comparison.missing ?? []).length > 0 ? <p>Stored missing fields: {llm.comparison.missing?.join(", ")}</p> : null}
                        <RawBlock title="Comparison payload" value={llm.comparison} />
                      </>
                    ) : <p>No comparison was stored.</p>}
                    {llm.evidence_check ? (
                      <p>
                        Evidence check grounded: {llm.evidence_check.is_grounded === undefined ? "unavailable" : llm.evidence_check.is_grounded ? "yes" : "no"}.
                        {(llm.evidence_check.unsupported_fields ?? []).length > 0
                          ? ` Unsupported fields: ${llm.evidence_check.unsupported_fields?.join(", ")}.`
                          : ""}
                      </p>
                    ) : null}
                    <EvidenceList items={llm.evidence ?? []} empty="No AI evidence was stored." />
                    <RawBlock title="AI candidate" value={llm.candidate} />
                  </>
                ) : (
                  <p>No Gemini-assisted extraction is stored for this document.</p>
                )}
              </Section>

              <Section title="Linked records">
                <ul className="space-y-2">
                  <li>{vendor ? `Vendor ${vendor.name}` : document.vendor_id ? "Vendor id is stored. The vendor record was not found." : "No vendor linked"}</li>
                  <li>{document.purchase_order_id ? <Link className="text-brand underline" href={`/purchase-orders/${document.purchase_order_id}`}>Purchase order</Link> : "No purchase order linked"}</li>
                  <li>{document.goods_receipt_id ? <Link className="text-brand underline" href={`/goods-receipts/${document.goods_receipt_id}`}>Goods receipt</Link> : "No goods receipt linked"}</li>
                  <li>{document.invoice_id ? <Link className="text-brand underline" href={`/invoices/${document.invoice_id}`}>Invoice</Link> : "No invoice linked"}</li>
                  <li>{review ? <Link className="text-brand underline" href={`/review/${review.id}`}>Review task</Link> : "No review task linked"}</li>
                </ul>
                {exceptions && exceptions.items.length > 0 ? (
                  <ul className="space-y-1">
                    {exceptions.items.map((item) => (
                      <li key={item.id}>
                        <Link className="text-brand underline" href={`/reconciliation/${item.id}`}>{item.exception_type}</Link>
                        <span className="text-ink-muted"> · {item.status}</span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p>No reconciliation exceptions reference the linked procurement record.</p>
                )}
              </Section>
            </>
          );
        }}
      </RecordState>
    </div>
  );
}
