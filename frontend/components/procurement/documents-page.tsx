"use client";

import Link from "next/link";
import { Suspense } from "react";

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

function DocumentsBody() {
  const query = useListQuery();
  const key = `documents:${query.q}:${query.documentType}:${query.status}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listDocuments(
        {
          q: query.q,
          document_type: query.documentType,
          status: query.status,
          limit: LIMIT,
          offset: query.offset,
        },
        signal,
      ),
    "Documents",
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Documents</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
          Persisted intake records. Status is the stored document lifecycle, not an extraction
          confidence score. Upload is not available on this page.
        </p>
      </div>
      <FilterBar
        fields={[
          { name: "q", label: "Filename" },
          { name: "document_type", label: "Document type", options: DOCUMENT_TYPES },
          { name: "status", label: "Status", options: DOCUMENT_STATUSES },
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
          <div className="space-y-3">
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
                  key: "status",
                  header: "Status",
                  cell: (row) => <EnumBadge value={row.status} kind="status" />,
                },
                {
                  key: "created",
                  header: "Created",
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
