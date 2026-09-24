"use client";

import Link from "next/link";
import { Suspense } from "react";

import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable, Pager } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { LoadingState } from "@/components/ui/state";
import { listPolicies } from "@/lib/api/policies";
import { formatTimestamp } from "@/lib/labels";

const LIMIT = 25;

function LibraryBody() {
  const query = useListQuery();
  const status = query.versionStatus;
  const key = `policies:${status}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listPolicies(
        { version_status: status || undefined, limit: LIMIT, offset: query.offset },
        signal,
      ),
    "Policies",
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Policy intelligence</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
          Stored policy documents and versions. A version status is not a reconciliation fact, and
          ACTIVE does not mean the version applies to every transaction.
        </p>
      </div>
      <FilterBar
        fields={[
          { name: "version_status", label: "Version status", options: ["DRAFT", "ACTIVE", "RETIRED"] },
        ]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading policies"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? {
                title: "No policies recorded",
                description: "No policy documents match this filter.",
              }
            : null
        }
      >
        {(data) => (
          <div className="space-y-3">
            <DataTable
              caption="Policy documents"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "name",
                  header: "Policy",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/policies/${row.id}`}>
                      {row.name}
                    </Link>
                  ),
                },
                {
                  key: "status",
                  header: "Active version status",
                  cell: (row) =>
                    row.active_version_count === 1 && row.active_status ? (
                      <EnumBadge value={row.active_status} kind="status" />
                    ) : row.active_version_count > 1 ? (
                      "Multiple active versions"
                    ) : (
                      "No single active version"
                    ),
                },
                {
                  key: "version",
                  header: "Active version",
                  cell: (row) => row.active_version_label ?? "Not selected",
                },
                {
                  key: "effective",
                  header: "Effective dates",
                  cell: (row) =>
                    row.effective_from
                      ? `${row.effective_from}${row.effective_to ? ` to ${row.effective_to}` : ""}`
                      : "See versions",
                },
                {
                  key: "count",
                  header: "Versions",
                  cell: (row) => row.version_count,
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

export function PolicyLibraryPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading policies" description="Preparing filters." />}>
      <LibraryBody />
    </Suspense>
  );
}
