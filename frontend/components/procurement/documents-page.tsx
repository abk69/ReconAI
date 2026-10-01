"use client";

import Link from "next/link";
import { Suspense, useRef, useState } from "react";

import { UploadDialog } from "@/components/documents/upload-dialog";
import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable, Pager } from "@/components/ui/data-table";
import { StatusBadge } from "@/components/ui/status-badge";
import { LoadingState } from "@/components/ui/state";
import { listDocuments } from "@/lib/api/procurement";
import { documentGuidance, documentKind, documentSetTags } from "@/lib/documents/next-action";

const LIMIT = 25;
const DOCUMENT_TYPES = [
  { value: "PO", label: "Purchase order" },
  { value: "GRN", label: "Goods receipt" },
  { value: "INVOICE", label: "Invoice" },
  { value: "UNKNOWN", label: "Unknown" },
];

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
          <h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">Documents</h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-muted">
            Upload a file, then follow the one step on its row. Save the purchase order before the goods receipt.
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
          { name: "document_type", label: "Type", options: DOCUMENT_TYPES },
        ]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading documents"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? {
                title: "No documents yet",
                description: "Upload a purchase order, a goods receipt, and an invoice.",
              }
            : null
        }
      >
        {(data) => (
          <div className="space-y-8">
            <DataTable
              caption="Documents"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "name",
                  header: "File",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/documents/${row.id}`}>
                      {row.original_filename}
                    </Link>
                  ),
                },
                {
                  key: "type",
                  header: "Type",
                  cell: (row) => {
                    const kind = documentKind(row.detected_type || row.document_type);
                    return kind.charAt(0).toUpperCase() + kind.slice(1);
                  },
                },
                {
                  key: "next",
                  header: "What to do",
                  cell: (row) => {
                    const guidance = documentGuidance(row);
                    const tags = documentSetTags(row);
                    return (
                      <span className="flex flex-col gap-2">
                        {tags.length > 0 ? (
                          <span className="flex flex-wrap gap-1.5">
                            {tags.map((tag) => (
                              <StatusBadge key={tag.label} label={tag.label} tone={tag.tone} />
                            ))}
                          </span>
                        ) : null}
                        <span>{guidance.sentence}</span>
                        {guidance.action ? (
                          <Link className="text-brand underline" href={`/documents/${row.id}`}>
                            {guidance.action}
                          </Link>
                        ) : null}
                      </span>
                    );
                  },
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
