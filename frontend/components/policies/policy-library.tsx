"use client";

import Link from "next/link";
import { Suspense } from "react";

import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { Pager } from "@/components/ui/data-table";
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
            <ul>
              {data.items.map((row) => (
                <li key={row.id} className="border-b border-white/8 py-6">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      <Link className="block text-2xl font-semibold tracking-tight text-ink" href={`/policies/${row.id}`}>
                        {row.name}
                      </Link>
                    </div>
                    {row.active_version_count === 1 && row.active_status ? (
                      <EnumBadge value={row.active_status} kind="status" />
                    ) : (
                      <p className="text-sm text-ink-muted">
                        {row.active_version_count > 1 ? "Multiple active versions" : "No single active version"}
                      </p>
                    )}
                  </div>
                  <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
                    <div>
                      <dt className="text-[11px] tracking-wide text-ink-faint uppercase">Active version</dt>
                      <dd className="mt-1">{row.active_version_label ?? "Not selected"}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] tracking-wide text-ink-faint uppercase">Effective dates</dt>
                      <dd className="mt-1">
                        {row.effective_from
                          ? `${row.effective_from}${row.effective_to ? ` to ${row.effective_to}` : ""}`
                          : "See versions"}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-[11px] tracking-wide text-ink-faint uppercase">Versions</dt>
                      <dd className="mt-1 tabular-nums">{row.version_count}</dd>
                    </div>
                    <div>
                      <dt className="text-[11px] tracking-wide text-ink-faint uppercase">Created</dt>
                      <dd className="mt-1">{formatTimestamp(row.created_at)}</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
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
