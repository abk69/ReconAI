"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable, Pager } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { LoadingState } from "@/components/ui/state";
import { listReviewTasks } from "@/lib/api/workflow";
import { formatTimestamp } from "@/lib/labels";
import type { ReviewTask } from "@/types/workflow";

const LIMIT = 25;
const STATUSES = ["PENDING", "IN_REVIEW", "APPROVED", "CORRECTED", "REJECTED"];
const TYPES = ["PO", "GRN", "INVOICE", "UNKNOWN"];
const PRIORITIES = ["LOW", "MEDIUM", "HIGH"];

function needsHuman(status: string): boolean {
  return status === "PENDING" || status === "IN_REVIEW";
}

function ordered(items: ReviewTask[], total: number): ReviewTask[] {
  if (total > items.length) {
    return items;
  }
  const rank = (status: string) => (status === "PENDING" ? 0 : status === "IN_REVIEW" ? 1 : 2);
  return [...items].sort((left, right) => rank(left.status) - rank(right.status));
}

function ReviewQueueBody() {
  const query = useListQuery();
  const params = useSearchParams();
  const priority = params.get("priority") ?? "";
  const key = `review:${query.q}:${query.status}:${query.documentType}:${priority}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listReviewTasks(
        {
          q: query.q,
          status: query.status,
          document_type: query.documentType,
          priority,
          limit: LIMIT,
          offset: query.offset,
        },
        signal,
      ),
    "Review tasks",
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Review center</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
          Human trust boundary for extraction. Pending and in-review tasks still need a person.
          Approving, correcting, or rejecting here does not run reconciliation or execute a
          resolution action.
        </p>
      </div>
      <FilterBar
        key={params.toString()}
        fields={[
          { name: "q", label: "Document filename" },
          { name: "status", label: "Review status", options: STATUSES },
          { name: "document_type", label: "Document type", options: TYPES },
          { name: "priority", label: "Priority", options: PRIORITIES },
        ]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading review tasks"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? {
                title: "No review tasks match this filter",
                description: "The review queue has no persisted tasks for these server-side filters.",
              }
            : null
        }
      >
        {(data) => {
          const rows = ordered(data.items, data.total);
          const openCount = rows.filter((row) => needsHuman(row.status)).length;
          return (
            <div className="space-y-3">
              <p className="text-sm text-ink">
                {query.status
                  ? `Filtered to ${query.status}.`
                  : data.total > data.items.length
                    ? "Newest tasks are listed first. Filter status to PENDING or IN_REVIEW to see open human work."
                    : `${openCount} ${openCount === 1 ? "task still needs" : "tasks still need"} a person on this page.`}
              </p>
              <DataTable
                caption="Extraction review tasks"
                rowKey={(row) => row.id}
                rows={rows}
                columns={[
                  {
                    key: "task",
                    header: "Review task",
                    cell: (row) => (
                      <Link className="text-brand underline" href={`/review/${row.id}`}>
                        {row.id.slice(0, 8)}
                      </Link>
                    ),
                  },
                  {
                    key: "document",
                    header: "Document",
                    cell: (row) => (
                      <Link className="text-brand underline" href={`/documents/${row.document_id}`}>
                        {row.original_filename ?? row.document_id}
                      </Link>
                    ),
                  },
                  {
                    key: "type",
                    header: "Detected type",
                    cell: (row) => row.detected_type ?? row.document_type ?? "Not detected",
                  },
                  {
                    key: "status",
                    header: "Status",
                    cell: (row) => (
                      <span className="inline-flex flex-col gap-1">
                        <EnumBadge value={row.status} kind="status" />
                        {needsHuman(row.status) ? (
                          <span className="text-xs text-ink">Needs human review</span>
                        ) : null}
                      </span>
                    ),
                  },
                  {
                    key: "reviewer",
                    header: "Assigned reviewer",
                    cell: (row) => row.assigned_to ?? "Unassigned",
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
          );
        }}
      </RecordState>
    </div>
  );
}

export function ReviewQueuePage() {
  return (
    <Suspense fallback={<LoadingState title="Loading review center" description="Preparing filters." />}>
      <ReviewQueueBody />
    </Suspense>
  );
}
