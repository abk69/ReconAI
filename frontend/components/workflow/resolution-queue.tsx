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
import { listResolutionPlans } from "@/lib/api/workflow";
import { formatTimestamp } from "@/lib/labels";

const LIMIT = 25;
const STATUSES = [
  "PROPOSED",
  "APPROVAL_REQUIRED",
  "APPROVED",
  "REJECTED",
  "EXECUTING",
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "NO_ACTION_RECOMMENDED",
];

function ResolutionQueueBody() {
  const query = useListQuery();
  const params = useSearchParams();
  const key = `plans:${query.status}:${query.offset}`;
  const state = useResource(
    key,
    (signal) => listResolutionPlans({ status: query.status, limit: LIMIT, offset: query.offset }, signal),
    "Resolution plans",
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Resolution</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
          Controlled workflow for stored plans: plan, proposed actions, human approval, execution,
          then result. Viewing this page does not approve or execute anything. An AI proposal is
          not authorization.
        </p>
        <ol className="mt-3 flex flex-wrap gap-2 text-xs text-ink-muted">
          {["Plan", "Actions", "Approval", "Execution", "Result"].map((step, index) => (
            <li key={step} className="rounded-md border border-line bg-surface px-2 py-1">
              {index + 1}. {step}
            </li>
          ))}
        </ol>
      </div>
      <FilterBar
        key={params.toString()}
        fields={[{ name: "status", label: "Plan status", options: STATUSES }]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading resolution plans"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? {
                title: "No resolution plans match this filter",
                description: "No persisted plans were found. This page does not create one.",
              }
            : null
        }
      >
        {(data) => (
          <div className="space-y-3">
            <DataTable
              caption="Resolution plans"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "plan",
                  header: "Plan",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/resolution/${row.id}`}>
                      AI-proposed plan
                    </Link>
                  ),
                },
                {
                  key: "status",
                  header: "Plan status",
                  cell: (row) => <EnumBadge value={row.status} kind="status" />,
                },
                {
                  key: "exception",
                  header: "Exception",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/exceptions/${row.reconciliation_exception_id}`}>
                      {row.exception_type ?? row.reconciliation_exception_id}
                    </Link>
                  ),
                },
                {
                  key: "actions",
                  header: "Proposed actions",
                  cell: (row) => `${row.action_count} stored`,
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

export function ResolutionQueuePage() {
  return (
    <Suspense fallback={<LoadingState title="Loading resolution" description="Preparing filters." />}>
      <ResolutionQueueBody />
    </Suspense>
  );
}
