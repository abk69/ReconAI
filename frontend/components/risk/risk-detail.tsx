"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { RiskScore } from "@/components/risk/risk-score";
import { DataTable } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { LoadingState } from "@/components/ui/state";
import { getRiskHistory, listAnomalies } from "@/lib/api/risk";
import { formatTimestamp } from "@/lib/labels";
import type { ContributingSignal, RiskProfile, TypeBreakdownRow } from "@/types/risk";

function recordHref(entityType: string, entityId: string): string | null {
  if (entityType === "INVOICE") return `/invoices/${entityId}`;
  if (entityType === "PURCHASE_ORDER") return `/purchase-orders/${entityId}`;
  return null;
}

function stored(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "Not stored";
  return String(value);
}

function Breakdown({ profile }: { profile: RiskProfile }) {
  const signals = profile.breakdown.contributing_signals ?? [];
  const types = profile.breakdown.type_breakdown ?? [];
  return (
    <div className="space-y-4">
      <section className="rounded-md border border-line bg-surface p-5">
        <h2 className="text-base font-semibold">Contribution breakdown</h2>
        <p className="mt-1 text-sm leading-6 text-ink-muted">
          Values are the stored M9 breakdown. This page does not recompute weights, multipliers, or
          caps.
        </p>
        {profile.breakdown.formula_notes ? (
          <p className="mt-2 text-sm">{profile.breakdown.formula_notes}</p>
        ) : null}
        {signals.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">No contributing signals were stored on this profile.</p>
        ) : (
          <div className="mt-3 overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <caption className="sr-only">Stored signal contributions</caption>
              <thead>
                <tr>
                  {[
                    "Type",
                    "Severity",
                    "Base weight",
                    "Severity multiplier",
                    "Recency multiplier",
                    "Raw contribution",
                    "Capped contribution",
                    "Signal",
                  ].map((header) => (
                    <th key={header} scope="col" className="px-2 py-1 text-xs uppercase text-ink-muted">
                      {header}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {signals.map((row) => (
                  <SignalRow key={row.signal_id ?? row.signal_fingerprint} row={row} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <section className="rounded-md border border-line bg-surface p-5">
        <h2 className="text-base font-semibold">Type caps</h2>
        <p className="mt-1 text-sm text-ink-muted">
          Caps are stored per anomaly type. A blank capped contribution on a signal line means the
          stored row did not include a per-signal cap.
        </p>
        {types.length === 0 ? (
          <p className="mt-3 text-sm text-ink-muted">No type breakdown was stored.</p>
        ) : (
          <ul className="mt-3 space-y-2 text-sm">
            {types.map((row) => (
              <TypeRow key={row.anomaly_type} row={row} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function SignalRow({ row }: { row: ContributingSignal }) {
  return (
    <tr className="border-t border-line">
      <td className="px-2 py-1">{stored(row.anomaly_type)}</td>
      <td className="px-2 py-1">{stored(row.severity)}</td>
      <td className="px-2 py-1">{stored(row.base_weight)}</td>
      <td className="px-2 py-1">{stored(row.severity_multiplier)}</td>
      <td className="px-2 py-1">{stored(row.recency_multiplier)}</td>
      <td className="px-2 py-1">{stored(row.raw_contribution)}</td>
      <td className="px-2 py-1">{stored(row.capped_contribution)}</td>
      <td className="px-2 py-1">
        {row.signal_id ? (
          <Link className="text-brand underline" href={`/risk/anomalies/${row.signal_id}`}>
            {row.signal_id.slice(0, 8)}
          </Link>
        ) : (
          "Not stored"
        )}
      </td>
    </tr>
  );
}

function TypeRow({ row }: { row: TypeBreakdownRow }) {
  return (
    <li>
      {stored(row.anomaly_type)}: contribution {stored(row.contribution)}, uncapped{" "}
      {stored(row.uncapped_contribution)}, cap {stored(row.cap)}, signals {stored(row.signal_count)}
    </li>
  );
}

function RiskDetailBody({ entityType, id }: { entityType: string; id: string }) {
  const params = useSearchParams();
  const router = useRouter();
  const asOf = params.get("as_of") ?? "";
  const [draft, setDraft] = useState(asOf);
  const history = useResource(
    `${entityType}:${id}:${asOf}`,
    (signal) => getRiskHistory(entityType, id, asOf || undefined, signal),
    "Risk profile",
  );
  const anomalyParams =
    entityType === "VENDOR"
      ? { vendor_id: id }
      : entityType === "INVOICE"
        ? { invoice_id: id }
        : { purchase_order_id: id };
  const anomalies = useResource(
    `signals:${entityType}:${id}`,
    (signal) => listAnomalies({ ...anomalyParams, limit: 25 }, signal),
    "Related anomalies",
  );
  const procurement = recordHref(entityType, id);

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={history} loadingTitle="Loading risk profile" empty={null}>
        {(data) => (
          <>
            <div>
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Risk score</p>
              <h1 className="mt-1 text-2xl font-semibold">
                {data.entity_type} {data.entity_label ?? data.entity_id}
              </h1>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                This profile stays within the {data.entity_type} scope stored by M9.
              </p>
              {procurement ? (
                <p className="mt-2 text-sm">
                  <Link className="text-brand underline" href={procurement}>
                    Open the procurement record
                  </Link>
                </p>
              ) : null}
            </div>

            <form
              className="rounded-md border border-line bg-surface p-5"
              onSubmit={(event) => {
                event.preventDefault();
                const next = new URLSearchParams(params.toString());
                if (draft) next.set("as_of", draft);
                else next.delete("as_of");
                router.push(next.size ? `?${next.toString()}` : "?");
              }}
            >
              <h2 className="text-base font-semibold">Point-in-time risk</h2>
              <p className="mt-1 text-sm leading-6 text-ink-muted">
                as_of selects a stored profile. A score of 0 with no signals is a stored result when
                that row exists. A missing row means no profile was saved for that date.
              </p>
              <label className="mt-3 flex flex-col gap-1 text-xs text-ink-muted">
                Point-in-time date
                <input
                  type="date"
                  className="rounded-md border border-line px-2 py-2 text-sm text-ink"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                />
              </label>
              <button type="submit" className="mt-3 rounded-md border border-line px-3 py-2 text-sm">
                Show stored profile
              </button>
            </form>

            {data.current ? (
              <div className="space-y-4">
                <RiskScore
                  score={data.current.score}
                  band={data.current.risk_band}
                  signalCount={data.current.signal_count}
                />
                <dl className="grid gap-3 rounded-md border border-line bg-surface p-5 text-sm sm:grid-cols-2">
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Score version</dt>
                    <dd className="mt-1">{data.current.score_version}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Point-in-time as_of</dt>
                    <dd className="mt-1">{data.current.as_of}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Calculated</dt>
                    <dd className="mt-1">{formatTimestamp(data.current.calculated_at)}</dd>
                  </div>
                  <div>
                    <dt className="text-xs uppercase text-ink-muted">Record identity</dt>
                    <dd className="mt-1 break-all text-xs">{data.current.fingerprint}</dd>
                  </div>
                </dl>
                <p className="text-sm text-ink-muted">{data.current.note}</p>
                <Breakdown profile={data.current} />
              </div>
            ) : (
              <p className="rounded-md border border-line bg-surface p-5 text-sm" role="status">
                {asOf
                  ? "No risk profile is stored for this point in time."
                  : "No risk profile is stored for this entity."}
              </p>
            )}

            <section className="rounded-md border border-line bg-surface p-5">
              <h2 className="text-base font-semibold">Profile history</h2>
              <p className="mt-1 text-sm text-ink-muted">
                Stored rows are immutable. Historical values were not recalculated from later signals.
              </p>
              {data.history.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">No historical profiles are stored.</p>
              ) : (
                <ol className="mt-3 space-y-3">
                  {data.history.map((row, index) => (
                    <li key={row.id} className="border-t border-line pt-3 text-sm">
                      <p className="text-xs uppercase text-ink-muted">
                        {index === 0 && !asOf ? "Latest stored profile" : `Stored profile ${row.as_of}`}
                      </p>
                      <p className="mt-1">
                        Risk score: {row.score} <EnumBadge value={row.risk_band} kind="severity" />
                      </p>
                      <p>{row.score_version}</p>
                      <p>{row.signal_count} contributing anomaly signals</p>
                      <p className="text-ink-muted">Calculated {formatTimestamp(row.calculated_at)}</p>
                    </li>
                  ))}
                </ol>
              )}
            </section>
          </>
        )}
      </RecordState>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Related anomaly signals</h2>
        <p className="text-sm text-ink-muted">Signals linked to this {entityType} only.</p>
        <RecordState state={anomalies} loadingTitle="Loading related anomalies" empty={null}>
          {(data) =>
            data.items.length === 0 ? (
              <p className="text-sm text-ink-muted">No anomaly signals are stored for this entity.</p>
            ) : (
              <DataTable
                caption="Related anomaly signals"
                rowKey={(row) => row.id}
                rows={data.items}
                columns={[
                  {
                    key: "type",
                    header: "Type",
                    cell: (row) => (
                      <Link className="text-brand underline" href={`/risk/anomalies/${row.id}`}>
                        {row.anomaly_type}
                      </Link>
                    ),
                  },
                  {
                    key: "severity",
                    header: "Severity",
                    cell: (row) => <EnumBadge value={row.severity} kind="severity" />,
                  },
                  { key: "explanation", header: "Explanation", cell: (row) => row.explanation },
                  {
                    key: "detected",
                    header: "Detected",
                    cell: (row) => formatTimestamp(row.detected_at),
                  },
                ]}
              />
            )
          }
        </RecordState>
      </section>
    </div>
  );
}

export function RiskDetailPage({ entityType, id }: { entityType: string; id: string }) {
  return (
    <Suspense fallback={<LoadingState title="Loading risk profile" description="Reading the stored profile." />}>
      <RiskDetailBody entityType={entityType} id={id} />
    </Suspense>
  );
}
