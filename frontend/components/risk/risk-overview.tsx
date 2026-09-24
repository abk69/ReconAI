"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { LoadingState } from "@/components/ui/state";
import {
  getAnomalySummary,
  getAnomalyTrends,
  listAnomalies,
  listRiskProfiles,
  listScans,
} from "@/lib/api/risk";
import { formatTimestamp } from "@/lib/labels";

const BANDS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const ANOMALY_TYPES = [
  "PRICE_VARIANCE",
  "QUANTITY_VARIANCE",
  "DUPLICATE_INVOICE",
  "TIMING_ANOMALY",
  "VENDOR_SPIKE",
  "REPEATED_MISMATCH",
];
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const ENTITY_TYPES = ["VENDOR", "INVOICE", "PURCHASE_ORDER"];

function riskHref(entityType: string, entityId: string): string | null {
  if (entityType === "VENDOR") return `/risk/vendors/${entityId}`;
  if (entityType === "INVOICE") return `/risk/invoices/${entityId}`;
  if (entityType === "PURCHASE_ORDER") return `/risk/purchase-orders/${entityId}`;
  return null;
}

function dayStart(value: string): string | undefined {
  return value ? `${value}T00:00:00Z` : undefined;
}

function dayEnd(value: string): string | undefined {
  return value ? `${value}T23:59:59Z` : undefined;
}

function RelatedRecords({
  row,
}: {
  row: {
    vendor_id: string | null;
    invoice_id: string | null;
    purchase_order_id: string | null;
  };
}) {
  const links = [
    row.vendor_id ? { href: `/risk/vendors/${row.vendor_id}`, label: "Vendor" } : null,
    row.invoice_id ? { href: `/invoices/${row.invoice_id}`, label: "Invoice" } : null,
    row.purchase_order_id
      ? { href: `/purchase-orders/${row.purchase_order_id}`, label: "PO" }
      : null,
  ].filter((item): item is { href: string; label: string } => item !== null);
  if (links.length === 0) return <span>No linked records</span>;
  return (
    <span className="flex flex-col gap-1">
      {links.map((link) => (
        <Link key={link.href} className="text-brand underline" href={link.href}>
          {link.label}
        </Link>
      ))}
    </span>
  );
}

function CountTable({ title, counts }: { title: string; counts: Record<string, number> }) {
  const rows = Object.entries(counts);
  const max = Math.max(0, ...rows.map(([, count]) => count));
  return (
    <div>
      <h3 className="text-[11px] font-medium tracking-[0.16em] text-ink-faint uppercase">{title}</h3>
      {rows.length === 0 ? (
        <p className="mt-3 text-sm text-ink-muted">No counts were returned.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {rows.map(([key, count]) => {
            const width = max === 0 ? 0 : Math.round((count / max) * 100);
            return (
              <li key={key}>
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <span>{key}</span>
                  <span className="tabular-nums">{count}</span>
                </div>
                <div className="mt-1.5 h-px bg-white/10" aria-hidden="true">
                  <div className="h-px bg-brand" style={{ width: `${width}%` }} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function RiskOverviewBody() {
  const params = useSearchParams();
  const query = useListQuery();
  const router = useRouter();
  const entityType = params.get("entity_type") ?? "";
  const riskBand = params.get("risk_band") ?? "";
  const profileOffset = Number(params.get("profile_offset") ?? "0") || 0;
  const anomalyType = params.get("anomaly_type") ?? "";
  const vendorId = params.get("vendor_id") ?? "";
  const invoiceId = params.get("invoice_id") ?? "";
  const purchaseOrderId = params.get("purchase_order_id") ?? "";
  const startDate = params.get("start_date") ?? "";
  const endDate = params.get("end_date") ?? "";
  const cursor = params.get("cursor") ?? "";

  const profiles = useResource(
    `profiles:${entityType}:${riskBand}:${profileOffset}`,
    (signal) =>
      listRiskProfiles(
        { entity_type: entityType, risk_band: riskBand, limit: 10, offset: profileOffset },
        signal,
      ),
    "Risk profiles",
  );
  const summary = useResource(
    `summary:${anomalyType}:${query.severity}:${vendorId}:${startDate}:${endDate}`,
    (signal) =>
      getAnomalySummary(
        {
          anomaly_type: anomalyType,
          severity: query.severity,
          vendor_id: vendorId,
          start_date: startDate,
          end_date: endDate,
        },
        signal,
      ),
    "Anomaly summary",
  );
  const priority = useResource(
    "priority",
    (signal) => listAnomalies({ high_or_critical: true, limit: 8 }, signal),
    "High-priority anomalies",
  );
  const anomalies = useResource(
    `anomalies:${anomalyType}:${query.severity}:${vendorId}:${invoiceId}:${purchaseOrderId}:${startDate}:${endDate}:${cursor}`,
    (signal) =>
      listAnomalies(
        {
          anomaly_type: anomalyType,
          severity: query.severity,
          vendor_id: vendorId,
          invoice_id: invoiceId,
          purchase_order_id: purchaseOrderId,
          detected_from: dayStart(startDate),
          detected_to: dayEnd(endDate),
          limit: 25,
          cursor,
        },
        signal,
      ),
    "Anomalies",
  );
  const trends = useResource(
    `trends:${startDate}:${endDate}`,
    (signal) => getAnomalyTrends({ period: "daily", start_date: startDate, end_date: endDate }, signal),
    "Anomaly trends",
  );
  const scans = useResource("scans", (signal) => listScans({ limit: 10 }, signal), "Scan jobs");

  function setBand(band: string) {
    const next = new URLSearchParams(params.toString());
    if (next.get("risk_band") === band) next.delete("risk_band");
    else next.set("risk_band", band);
    next.delete("profile_offset");
    router.push(next.size ? `?${next.toString()}` : "?");
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <div>
        <p className="text-[11px] font-medium tracking-[0.2em] text-ink-faint uppercase">Risk intelligence</p>
        <h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">Stored risk, by entity.</h1>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-ink-muted">
          An anomaly is a deterministic signal from a stored rule. A risk score is a stored
          aggregation of those signals. Deterministic risk signal — not a probability of fraud.
        </p>
      </div>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Risk band summary</h2>
        <p className="text-sm text-ink-muted">
          Counts use the latest stored profile for each entity and score version. Older profiles are
          not counted again.
        </p>
        <RecordState state={profiles} loadingTitle="Loading risk profiles" empty={null}>
          {(data) => (
            <>
              <div aria-label="Risk band counts">
                <ul className="space-y-3">
                  {BANDS.map((band) => {
                    const count = data.counts_by_band[band] ?? 0;
                    const max = Math.max(1, ...BANDS.map((item) => data.counts_by_band[item] ?? 0));
                    const width = Math.round((count / max) * 100);
                    return (
                      <li key={band}>
                        <button
                          type="button"
                          className="flex w-full items-center gap-4 text-left"
                          aria-pressed={riskBand === band}
                          onClick={() => setBand(band)}
                        >
                          <span className="w-24 text-[11px] tracking-[0.14em] text-ink-faint uppercase">{band}</span>
                          <span className="relative h-px flex-1 bg-white/10" aria-hidden="true">
                            <span className="absolute inset-y-0 left-0 bg-brand" style={{ width: `${width}%` }} />
                          </span>
                          <span className="w-8 text-right text-sm tabular-nums">{count}</span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </div>
              {data.total === 0 ? (
                <p className="text-sm text-ink-muted">No risk profiles are stored for this filter.</p>
              ) : (
                <DataTable
                  caption="Recent risk profiles"
                  rowKey={(row) => row.id}
                  rows={data.items}
                  columns={[
                    {
                      key: "entity",
                      header: "Entity",
                      cell: (row) => {
                        const href = riskHref(row.entity_type, row.entity_id);
                        const label = row.entity_label ?? row.entity_id;
                        return href ? (
                          <Link className="text-brand underline" href={href}>
                            {row.entity_type} {label}
                          </Link>
                        ) : (
                          label
                        );
                      },
                    },
                    { key: "score", header: "Score", cell: (row) => `Risk score: ${row.score}` },
                    {
                      key: "band",
                      header: "Band",
                      cell: (row) => <EnumBadge value={row.risk_band} kind="severity" />,
                    },
                    { key: "signals", header: "Signals", cell: (row) => String(row.signal_count) },
                    { key: "version", header: "Score version", cell: (row) => row.score_version },
                    {
                      key: "calculated",
                      header: "Calculated",
                      cell: (row) => formatTimestamp(row.calculated_at),
                    },
                  ]}
                />
              )}
            </>
          )}
        </RecordState>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Anomaly overview</h2>
        <RecordState state={summary} loadingTitle="Loading anomaly summary" empty={null}>
          {(data) =>
            data.total_signals === 0 ? (
              <p className="text-sm text-ink-muted">No anomaly signals match this summary filter.</p>
            ) : (
              <div className="grid gap-10 lg:grid-cols-2">
                <CountTable title="Anomaly signals by type" counts={data.counts_by_type} />
                <CountTable title="Anomaly signals by severity" counts={data.counts_by_severity} />
              </div>
            )
          }
        </RecordState>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">High-priority signals</h2>
        <p className="text-sm text-ink-muted">Recent stored signals with severity HIGH or CRITICAL.</p>
        <RecordState state={priority} loadingTitle="Loading high-priority signals" empty={null}>
          {(data) =>
            data.items.length === 0 ? (
              <p className="text-sm text-ink-muted">No high-priority anomaly signals are stored.</p>
            ) : (
              <DataTable
                caption="High and critical anomaly signals"
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
                  {
                    key: "entity",
                    header: "Affected records",
                    cell: (row) => <RelatedRecords row={row} />,
                  },
                  { key: "title", header: "Explanation", cell: (row) => row.explanation },
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

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Anomaly queue</h2>
        <FilterBar
          key={params.toString()}
          fields={[
            { name: "anomaly_type", label: "Anomaly type", options: ANOMALY_TYPES },
            { name: "severity", label: "Severity", options: SEVERITIES },
            { name: "entity_type", label: "Risk entity type", options: ENTITY_TYPES },
            { name: "vendor_id", label: "Vendor id" },
            { name: "invoice_id", label: "Invoice id" },
            { name: "purchase_order_id", label: "Purchase order id" },
            { name: "start_date", label: "Detected from (YYYY-MM-DD)" },
            { name: "end_date", label: "Detected to (YYYY-MM-DD)" },
          ]}
        />
        <RecordState state={anomalies} loadingTitle="Loading anomalies" empty={null}>
          {(data) =>
            data.items.length === 0 ? (
              <p className="text-sm text-ink-muted">No anomaly signals match these server-side filters.</p>
            ) : (
              <div className="space-y-3">
                <DataTable
                  caption="Anomaly signals"
                  rowKey={(row) => row.id}
                  rows={data.items}
                  columns={[
                    {
                      key: "type",
                      header: "Type",
                      cell: (row) => (
                        <Link className="text-brand underline" href={`/risk/anomalies/${row.id}`}>
                          {row.title || row.anomaly_type}
                        </Link>
                      ),
                    },
                    {
                      key: "severity",
                      header: "Severity",
                      cell: (row) => <EnumBadge value={row.severity} kind="severity" />,
                    },
                    {
                      key: "entity",
                      header: "Affected records",
                      cell: (row) => <RelatedRecords row={row} />,
                    },
                    { key: "explanation", header: "Explanation", cell: (row) => row.explanation },
                    {
                      key: "detected",
                      header: "Detected",
                      cell: (row) => formatTimestamp(row.detected_at),
                    },
                  ]}
                />
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-50"
                    disabled={!cursor}
                    onClick={() => {
                      const next = new URLSearchParams(params.toString());
                      next.delete("cursor");
                      router.push(next.size ? `?${next.toString()}` : "?");
                    }}
                  >
                    First page
                  </button>
                  <button
                    type="button"
                    className="rounded-md border border-line px-3 py-2 text-sm disabled:opacity-50"
                    disabled={!data.next_cursor}
                    onClick={() => {
                      if (!data.next_cursor) return;
                      const next = new URLSearchParams(params.toString());
                      next.set("cursor", data.next_cursor);
                      router.push(`?${next.toString()}`);
                    }}
                  >
                    Next page
                  </button>
                </div>
              </div>
            )
          }
        </RecordState>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Trend</h2>
        <p className="text-sm text-ink-muted">
          Periods are only those returned by the analytics API. A smaller count is a stored total, not
          a security conclusion.
        </p>
        <RecordState state={trends} loadingTitle="Loading anomaly trends" empty={null}>
          {(data) =>
            data.points.length === 0 ? (
              <p className="text-sm text-ink-muted">No trend periods were returned.</p>
            ) : (
              <DataTable
                caption="Anomaly counts by period"
                rowKey={(row) => row.period}
                rows={data.points}
                columns={[
                  { key: "period", header: "Period", cell: (row) => row.period },
                  { key: "count", header: "Signals", cell: (row) => String(row.count) },
                  {
                    key: "high",
                    header: "High or critical",
                    cell: (row) => String(row.high_or_critical),
                  },
                ]}
              />
            )
          }
        </RecordState>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Scan jobs</h2>
        <p className="text-sm text-ink-muted">Stored scan status. This page does not start a scan.</p>
        <RecordState state={scans} loadingTitle="Loading scan jobs" empty={null}>
          {(data) =>
            data.total === 0 ? (
              <p className="text-sm text-ink-muted">No scan jobs are stored.</p>
            ) : (
              <DataTable
                caption="Anomaly scan jobs"
                rowKey={(row) => row.id}
                rows={data.items}
                columns={[
                  { key: "type", header: "Scan type", cell: (row) => row.scan_type },
                  {
                    key: "status",
                    header: "Status",
                    cell: (row) => <EnumBadge value={row.status} kind="status" />,
                  },
                  { key: "processed", header: "Processed", cell: (row) => String(row.processed_count) },
                  { key: "anomalies", header: "Anomalies", cell: (row) => String(row.anomaly_count) },
                  {
                    key: "requested",
                    header: "Requested",
                    cell: (row) => formatTimestamp(row.requested_at),
                  },
                  {
                    key: "completed",
                    header: "Completed",
                    cell: (row) => (row.completed_at ? formatTimestamp(row.completed_at) : "Not completed"),
                  },
                  {
                    key: "error",
                    header: "Error",
                    cell: (row) => row.error_message ?? (row.error_count ? `${row.error_count} errors` : "None"),
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

export function RiskOverviewPage() {
  return (
    <Suspense fallback={<LoadingState title="Loading risk intelligence" description="Preparing filters." />}>
      <RiskOverviewBody />
    </Suspense>
  );
}
