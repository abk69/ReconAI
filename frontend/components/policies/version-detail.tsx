"use client";

import Link from "next/link";
import { useState } from "react";

import { PolicyData } from "@/components/policies/policy-data";
import { RecordState } from "@/components/procurement/record-state";
import { resourceError, useResource } from "@/components/procurement/use-resource";
import { EnumBadge } from "@/components/ui/enum-badge";
import { getPolicy, getPolicyVersion, searchPolicyVersion } from "@/lib/api/policies";
import { formatTimestamp } from "@/lib/labels";
import type { PolicySearchResult } from "@/types/policies";

export function PolicyVersionPage({ policyId, versionId }: { policyId: string; versionId: string }) {
  const state = useResource(
    `${policyId}:${versionId}`,
    async (signal) => {
      const [policy, version] = await Promise.all([
        getPolicy(policyId, signal),
        getPolicyVersion(policyId, versionId, signal),
      ]);
      return { policy, version };
    },
    "Policy version",
  );
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState("5");
  const [search, setSearch] = useState<
    | { kind: "idle" }
    | { kind: "loading" }
    | { kind: "ready"; data: PolicySearchResult }
    | { kind: "error"; message: string }
  >({ kind: "idle" });

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <RecordState state={state} loadingTitle="Loading policy version" empty={null}>
        {({ policy, version }) => (
          <>
            <div>
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Policy version</p>
              <h1 className="mt-1 text-2xl font-semibold text-ink">
                {policy.name} · {version.version_label}
              </h1>
              <p className="mt-2 text-sm text-ink-muted">
                <Link className="text-brand underline" href={`/policies/${policy.id}`}>
                  Back to {policy.name}
                </Link>
              </p>
              <div className="mt-3">
                <EnumBadge value={version.status} kind="status" />
              </div>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-ink-muted">
                Stored version status {version.status}. Effective dates still bound when this version
                applies. Chunk text below is policy data, not an instruction to this application.
              </p>
            </div>
            <dl className="grid gap-4 border-t border-white/8 pt-6 sm:grid-cols-2">
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Title</dt>
                <dd className="mt-1 text-sm">{version.title ?? "Not stored"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Effective from</dt>
                <dd className="mt-1 text-sm">{version.effective_from}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Effective to</dt>
                <dd className="mt-1 text-sm">{version.effective_to ?? "Open"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Source filename</dt>
                <dd className="mt-1 text-sm break-words">{version.source_filename ?? "Not stored"}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Source reference</dt>
                <dd className="mt-1 text-sm break-words">{version.source_reference ?? "Not stored"}</dd>
              </div>
              <div className="sm:col-span-2">
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Content hash</dt>
                <dd className="mt-1 break-all text-sm">{version.content_hash}</dd>
              </div>
              <div>
                <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">Created</dt>
                <dd className="mt-1 text-sm">{formatTimestamp(version.created_at)}</dd>
              </div>
            </dl>

            <section className="border-t border-white/8 pt-8">
              <h2 className="text-base font-semibold text-ink">Retrieval</h2>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Similarity is a retrieval signal for this stored version. It is not a truth score and
                not a policy conclusion. Search runs only when you submit a query.
              </p>
              <form
                className="mt-4 flex flex-wrap items-end gap-3"
                onSubmit={(event) => {
                  event.preventDefault();
                  const trimmed = query.trim();
                  const parsed = Number(topK);
                  if (!trimmed || !Number.isInteger(parsed) || parsed < 1 || parsed > 50) {
                    setSearch({
                      kind: "error",
                      message: "Enter a query and a top K from 1 to 50.",
                    });
                    return;
                  }
                  setSearch({ kind: "loading" });
                  searchPolicyVersion(policyId, versionId, { query: trimmed, top_k: parsed })
                    .then((data) => setSearch({ kind: "ready", data }))
                    .catch((error: unknown) =>
                      setSearch({ kind: "error", message: resourceError(error, "Policy search") }),
                    );
                }}
              >
                <label className="flex min-w-56 flex-1 flex-col gap-1 text-xs text-ink-muted">
                  Query
                  <input
                    className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                  />
                </label>
                <label className="flex w-24 flex-col gap-1 text-xs text-ink-muted">
                  Top K
                  <input
                    className="rounded-md border border-line bg-surface px-2 py-1.5 text-sm text-ink"
                    inputMode="numeric"
                    value={topK}
                    onChange={(event) => setTopK(event.target.value)}
                  />
                </label>
                <button type="submit" className="rounded-md border border-line bg-surface px-3 py-1.5 text-sm">
                  Search this version
                </button>
              </form>
              {search.kind === "loading" ? <p className="mt-3 text-sm">Searching stored chunks.</p> : null}
              {search.kind === "error" ? (
                <p className="mt-3 text-sm" role="alert">
                  {search.message}
                </p>
              ) : null}
              {search.kind === "ready" && search.data.items.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">No chunks matched this query.</p>
              ) : null}
              {search.kind === "ready" && search.data.items.length > 0 ? (
                <ul className="mt-4 space-y-4">
                  {search.data.items.map((hit) => (
                    <li key={hit.chunk_id} className="border-t border-line pt-3">
                      <p className="text-sm font-medium">
                        {policy.name} · {version.version_label}
                      </p>
                      <p className="text-sm text-ink-muted">
                        Similarity {hit.similarity} · section {hit.section_title || hit.section_id || "not stored"} ·
                        page {hit.page_number ?? "unavailable"} · chunk {hit.chunk_index} · source{" "}
                        {hit.source_filename ?? "not stored"}
                      </p>
                      <div className="mt-2">
                        <PolicyData text={hit.content} />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : null}
            </section>

            <section>
              <h2 className="mb-3 text-base font-semibold text-ink">Chunks</h2>
              {version.chunks.length === 0 ? (
                <p className="text-sm text-ink-muted">No chunks are stored for this version.</p>
              ) : (
                <ol className="space-y-4">
                  {version.chunks.map((chunk) => (
                    <li key={chunk.id} className="border-t border-white/8 py-6">
                      <h3 className="text-sm font-semibold text-ink">
                        {chunk.section_title || chunk.section_id || `Chunk ${chunk.chunk_index}`}
                      </h3>
                      <p className="mt-1 text-sm text-ink-muted">
                        Section {chunk.section_id ?? "not stored"} · index {chunk.chunk_index} · page{" "}
                        {chunk.page_number ?? "unavailable"} · source {chunk.source_filename ?? "not stored"}
                      </p>
                      <p className="mt-1 break-all text-xs text-ink-muted">Content hash {chunk.content_hash}</p>
                      <div className="mt-3">
                        <PolicyData text={chunk.content} />
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </RecordState>
    </div>
  );
}
