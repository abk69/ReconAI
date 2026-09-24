"use client";

import Link from "next/link";

import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { getPolicy, listPolicyVersions } from "@/lib/api/policies";
import { formatTimestamp } from "@/lib/labels";

export function PolicyDetailPage({ id }: { id: string }) {
  const state = useResource(
    id,
    async (signal) => {
      const [policy, versions] = await Promise.all([
        getPolicy(id, signal),
        listPolicyVersions(id, signal),
      ]);
      return { policy, versions };
    },
    "Policy",
  );

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <RecordState state={state} loadingTitle="Loading policy" empty={null}>
        {({ policy, versions }) => (
          <>
            <div>
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Policy document</p>
              <h1 className="mt-1 text-2xl font-semibold text-ink">{policy.name}</h1>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
                {policy.description || "No description is stored."} Versions stay separate. This page
                does not merge them into one document.
              </p>
            </div>
            <dl className="grid gap-4 border-t border-white/8 pt-6 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Policy id</dt>
                <dd className="mt-1 break-all text-sm">{policy.id}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Created</dt>
                <dd className="mt-1 text-sm">{formatTimestamp(policy.created_at)}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Versions</dt>
                <dd className="mt-1 text-sm">{versions.count}</dd>
              </div>
            </dl>
            <section>
              <h2 className="mb-3 text-base font-semibold text-ink">Versions</h2>
              <p className="mb-3 text-sm leading-6 text-ink-muted">
                ACTIVE is a stored version status. Effective dates still determine when a version
                applies. This page does not choose the newest version.
              </p>
              {versions.items.length === 0 ? (
                <p className="text-sm text-ink-muted">No versions are stored for this policy.</p>
              ) : (
                <DataTable
                  caption="Policy versions"
                  rowKey={(row) => row.id}
                  rows={versions.items}
                  columns={[
                    {
                      key: "label",
                      header: "Version",
                      cell: (row) => (
                        <Link className="text-brand underline" href={`/policies/${id}/versions/${row.id}`}>
                          {row.version_label}
                        </Link>
                      ),
                    },
                    {
                      key: "status",
                      header: "Status",
                      cell: (row) => <EnumBadge value={row.status} kind="status" />,
                    },
                    {
                      key: "from",
                      header: "Effective from",
                      cell: (row) => row.effective_from,
                    },
                    {
                      key: "to",
                      header: "Effective to",
                      cell: (row) => row.effective_to ?? "Open",
                    },
                    {
                      key: "source",
                      header: "Source filename",
                      cell: (row) => row.source_filename ?? "Not stored",
                    },
                    {
                      key: "chunks",
                      header: "Chunks",
                      cell: (row) => row.chunk_count ?? 0,
                    },
                  ]}
                />
              )}
            </section>
          </>
        )}
      </RecordState>
    </div>
  );
}
