"use client";

import Link from "next/link";
import { Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable, Pager } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { LoadingState } from "@/components/ui/state";
import { listExceptions } from "@/lib/api/procurement";
import { formatTimestamp } from "@/lib/labels";

const LIMIT = 25;
const STATUSES = ["OPEN", "IN_REVIEW", "RESOLVED", "DISMISSED"];
const SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const TYPES = [
  "QUANTITY_MISMATCH",
  "PRICE_MISMATCH",
  "TAX_MISMATCH",
  "IDENTIFIER_MISMATCH",
  "DUPLICATE_INVOICE",
  "DATE_MISMATCH",
  "MISSING_DOCUMENT",
  "OTHER",
];

function ReconciliationBody({
  detailBase,
  title,
  description,
  emptyTitle,
  emptyDescription,
}: {
  detailBase: string;
  title: string;
  description: string;
  emptyTitle: string;
  emptyDescription: string;
}) {
  const query = useListQuery();
  const params = useSearchParams();
  const router = useRouter();
  const key = `ex:${query.q}:${query.status}:${query.severity}:${query.exceptionType}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listExceptions(
        {
          q: query.q,
          status: query.status,
          severity: query.severity,
          exception_type: query.exceptionType,
          limit: LIMIT,
          offset: query.offset,
        },
        signal,
      ),
    "Reconciliation exceptions",
  );

  function setStatus(status: string) {
    const next = new URLSearchParams(params.toString());
    if (status && next.get("status") !== status) {
      next.set("status", status);
    } else {
      next.delete("status");
    }
    next.delete("offset");
    router.push(`?${next.toString()}`);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">{description}</p>
      </div>
      <FilterBar
        key={params.toString()}
        fields={[
          { name: "q", label: "Invoice, PO, or GRN number" },
          { name: "status", label: "Status", options: STATUSES },
          { name: "severity", label: "Severity", options: SEVERITIES },
          { name: "exception_type", label: "Exception type", options: TYPES },
        ]}
      />
      {state.kind === "ready" ? (
        <div className="flex flex-wrap gap-2" aria-label="Exception status counts">
          {STATUSES.map((status) => (
            <button
              key={status}
              type="button"
              className="rounded-md border border-line bg-surface px-3 py-2 text-left"
              aria-pressed={query.status === status}
              onClick={() => setStatus(status)}
            >
              <span className="block text-xs text-ink-muted">{status}</span>
              <span className="text-lg font-semibold tabular-nums text-ink">
                {state.data.counts_by_status[status] ?? 0}
              </span>
            </button>
          ))}
        </div>
      ) : null}
      <RecordState
        state={state}
        loadingTitle="Loading reconciliation exceptions"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? {
                title: emptyTitle,
                description: emptyDescription,
              }
            : null
        }
      >
        {(data) => (
          <div className="space-y-3">
            <DataTable
              caption="Reconciliation exceptions"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "type",
                  header: "Type",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`${detailBase}/${row.id}`}>
                      {row.exception_type}
                    </Link>
                  ),
                },
                {
                  key: "severity",
                  header: "Severity",
                  cell: (row) => <EnumBadge value={row.severity} kind="severity" />,
                },
                {
                  key: "invoice",
                  header: "Invoice",
                  cell: (row) =>
                    row.invoice_id ? (
                      <Link className="text-brand underline" href={`/invoices/${row.invoice_id}`}>
                        {row.invoice_number ?? row.invoice_id}
                      </Link>
                    ) : (
                      "None"
                    ),
                },
                {
                  key: "po",
                  header: "PO",
                  cell: (row) =>
                    row.purchase_order_id ? (
                      <Link className="text-brand underline" href={`/purchase-orders/${row.purchase_order_id}`}>
                        {row.po_number ?? row.purchase_order_id}
                      </Link>
                    ) : (
                      "None"
                    ),
                },
                {
                  key: "grn",
                  header: "GRN",
                  cell: (row) =>
                    row.goods_receipt_id ? (
                      <Link className="text-brand underline" href={`/goods-receipts/${row.goods_receipt_id}`}>
                        {row.grn_number ?? row.goods_receipt_id}
                      </Link>
                    ) : (
                      "None"
                    ),
                },
                { key: "message", header: "Message", cell: (row) => row.message },
                { key: "status", header: "Status", cell: (row) => <EnumBadge value={row.status} kind="status" /> },
                { key: "created", header: "Created", cell: (row) => formatTimestamp(row.created_at) },
              ]}
            />
            <Pager offset={query.offset} limit={LIMIT} total={data.total} onPage={query.setOffset} />
          </div>
        )}
      </RecordState>
    </div>
  );
}

export function ReconciliationPage({
  detailBase = "/reconciliation",
  title = "Reconciliation",
  description = "Persisted results from the deterministic reconciliation engine. This page does not decide whether records match and does not load policy or AI explanations.",
  emptyTitle = "No reconciliation exceptions recorded",
  emptyDescription = "No persisted exceptions match this filter. A match that was never stored is not shown as a success count.",
  loadingTitle = "Loading reconciliation",
}: {
  detailBase?: string;
  title?: string;
  description?: string;
  emptyTitle?: string;
  emptyDescription?: string;
  loadingTitle?: string;
}) {
  return (
    <Suspense fallback={<LoadingState title={loadingTitle} description="Preparing filters." />}>
      <ReconciliationBody
        detailBase={detailBase}
        title={title}
        description={description}
        emptyTitle={emptyTitle}
        emptyDescription={emptyDescription}
      />
    </Suspense>
  );
}
