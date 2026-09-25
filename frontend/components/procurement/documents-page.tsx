"use client";

import Link from "next/link";
import { Suspense, useRef, useState } from "react";

import { UploadDialog } from "@/components/documents/upload-dialog";
import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable, Pager } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { LoadingState } from "@/components/ui/state";
import { listDocuments } from "@/lib/api/procurement";
import { formatTimestamp } from "@/lib/labels";

const LIMIT = 25;
const DOCUMENT_TYPES = ["PO", "GRN", "INVOICE", "UNKNOWN"];
const DOCUMENT_STATUSES = [
  "UPLOADED",
  "VALIDATED",
  "EXTRACTION_PENDING",
  "EXTRACTING",
  "EXTRACTED",
  "NORMALIZED",
  "READY_FOR_RECONCILIATION",
  "EXTRACTION_FAILED",
  "VALIDATION_FAILED",
  "REVIEW_REQUIRED",
  "REVIEW_REJECTED",
];
const EXTRACTION_OUTCOMES = [
  "READY_FOR_RECONCILIATION",
  "REVIEW_REQUIRED",
  "VALIDATION_FAILED",
  "EXTRACTION_FAILED",
];
const REVIEW_STATUSES = ["PENDING", "IN_REVIEW", "APPROVED", "CORRECTED", "REJECTED"];

const PROCESSING_STAGES: [string, string[]][] = [
  ["Intake", ["UPLOADED", "VALIDATED", "VALIDATION_FAILED"]],
  ["Extraction", ["EXTRACTION_PENDING", "EXTRACTING", "EXTRACTED", "NORMALIZED", "EXTRACTION_FAILED"]],
  ["Review", ["REVIEW_REQUIRED", "REVIEW_REJECTED"]],
  ["Authoritative", ["READY_FOR_RECONCILIATION"]],
];

function ProcessingSignals({ items }: { items: { status: string }[] }) {
  const stages = PROCESSING_STAGES.map(([label, statuses]) => ({
    label,
    count: items.filter((item) => statuses.includes(item.status)).length,
  }));
  const known = stages.reduce((sum, stage) => sum + stage.count, 0);
  const other = items.length - known;
  const max = Math.max(1, ...stages.map((stage) => stage.count), other);
  return (
    <section aria-label="Processing signals">
      <h2 className="text-[11px] font-medium tracking-[0.16em] text-ink-faint uppercase">Processing signals</h2>
      <p className="mt-2 max-w-2xl text-sm text-ink-muted">
        Stored document statuses on this page. This is not a system-wide total.
      </p>
      <ol className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stages.map((stage, index) => (
          <li key={stage.label}>
            <p className="text-[11px] tracking-[0.14em] text-ink-faint uppercase">
              {String(index + 1).padStart(2, "0")} {stage.label}
            </p>
            <p className="mt-1 text-2xl font-semibold tabular-nums">{stage.count}</p>
            <div className="mt-2 h-px bg-white/10" aria-hidden="true">
              <div className="h-px bg-brand" style={{ width: `${Math.round((stage.count / max) * 100)}%` }} />
            </div>
          </li>
        ))}
      </ol>
      {other > 0 ? <p className="mt-3 text-sm text-ink-muted">{other} documents on this page use another stored status.</p> : null}
    </section>
  );
}

function DocumentsBody() {
  const query = useListQuery();
  const uploadButtonRef = useRef<HTMLButtonElement>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadVersion, setUploadVersion] = useState(0);
  const key = `documents:${uploadVersion}:${query.q}:${query.documentType}:${query.status}:${query.extractionOutcome}:${query.reviewStatus}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listDocuments(
        {
          q: query.q,
          document_type: query.documentType,
          status: query.status,
          extraction_outcome: query.extractionOutcome,
          review_status: query.reviewStatus,
          limit: LIMIT,
          offset: query.offset,
        },
        signal,
      ),
    "Documents",
  );

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-[11px] font-medium tracking-[0.2em] text-ink-faint uppercase">Document intelligence</p>
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">Documents</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-muted">
            Persisted intake records. Current document status, extraction outcome, and review status
            are stored facts. An extraction candidate is not an authoritative procurement record.
          </p>
        </div>
        <button
          ref={uploadButtonRef}
          type="button"
          className="min-h-10 rounded-lg bg-brand px-3 py-2 text-sm text-on-brand"
          onClick={() => setUploadOpen(true)}
        >
          Upload document
        </button>
      </div>
      <UploadDialog
        open={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          uploadButtonRef.current?.focus();
        }}
        onUploaded={() => setUploadVersion((version) => version + 1)}
      />
      <FilterBar
        fields={[
          { name: "q", label: "Filename" },
          { name: "document_type", label: "Document type", options: DOCUMENT_TYPES },
          { name: "status", label: "Document status", options: DOCUMENT_STATUSES },
          { name: "extraction_outcome", label: "Extraction outcome", options: EXTRACTION_OUTCOMES },
          { name: "review_status", label: "Review status", options: REVIEW_STATUSES },
        ]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading documents"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? {
                title: "No documents recorded",
                description: "No documents match this filter. Nothing has been invented to fill the list.",
              }
            : null
        }
      >
        {(data) => (
          <div className="space-y-8">
            <ProcessingSignals items={data.items} />
            <DataTable
              caption="Documents"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "name",
                  header: "Filename",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/documents/${row.id}`}>
                      {row.original_filename}
                    </Link>
                  ),
                },
                {
                  key: "type",
                  header: "Type",
                  cell: (row) => <EnumBadge value={row.document_type} kind="status" />,
                },
                {
                  key: "detected",
                  header: "Detected type",
                  cell: (row) => row.detected_type ?? "Not stored",
                },
                {
                  key: "status",
                  header: "Document status",
                  cell: (row) => <EnumBadge value={row.status} kind="status" />,
                },
                {
                  key: "extraction",
                  header: "Extraction outcome",
                  cell: (row) => row.extraction_outcome ?? "Not stored",
                },
                {
                  key: "review",
                  header: "Review status",
                  cell: (row) => row.review_status ?? "No review task",
                },
                {
                  key: "links",
                  header: "Linked records",
                  cell: (row) => (
                    <span className="flex flex-col gap-1">
                      {row.purchase_order_id ? <Link className="text-brand underline" href={`/purchase-orders/${row.purchase_order_id}`}>Purchase order</Link> : null}
                      {row.goods_receipt_id ? <Link className="text-brand underline" href={`/goods-receipts/${row.goods_receipt_id}`}>Goods receipt</Link> : null}
                      {row.invoice_id ? <Link className="text-brand underline" href={`/invoices/${row.invoice_id}`}>Invoice</Link> : null}
                      {!row.purchase_order_id && !row.goods_receipt_id && !row.invoice_id ? "None linked" : null}
                    </span>
                  ),
                },
                {
                  key: "created",
                  header: "Uploaded",
                  cell: (row) => formatTimestamp(row.created_at),
                },
              ]}
            />
            <Pager offset={query.offset} limit={LIMIT} total={data.total} onPage={query.setOffset} />
          </div>
        )}
      </RecordState>
    </div>
  );
}

export function DocumentsPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading documents" description="Preparing filters." />}>
      <DocumentsBody />
    </Suspense>
  );
}
