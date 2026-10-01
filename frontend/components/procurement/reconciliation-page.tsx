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

const STATUS_LABELS: Record<string, string> = {
  OPEN: "Open",
  IN_REVIEW: "In review",
  RESOLVED: "Resolved",
  DISMISSED: "Dismissed",
};

const EXCEPTION_LABELS: Record<string, string> = {
  QUANTITY_MISMATCH: "Quantity does not match",
  PRICE_MISMATCH: "Price does not match",
  TAX_MISMATCH: "Tax does not match",
  IDENTIFIER_MISMATCH: "Identifier does not match",
  DUPLICATE_INVOICE: "Duplicate invoice",
  DATE_MISMATCH: "Date does not match",
  MISSING_DOCUMENT: "A document is missing",
  OTHER: "Other problem",
};

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
          {
            name: "status",
            label: "Status",
            options: STATUSES.map((status) => ({ value: status, label: STATUS_LABELS[status] ?? status })),
          },
          {
            name: "severity",
            label: "Severity",
            options: SEVERITIES.map((severity) => ({
              value: severity,
              label: severity.charAt(0) + severity.slice(1).toLowerCase(),
            })),
          },
          {
            name: "exception_type",
            label: "Problem",
            options: TYPES.map((type) => ({ value: type, label: EXCEPTION_LABELS[type] ?? type })),
          },
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
              <span className="block text-xs text-ink-muted">{STATUS_LABELS[status] ?? status}</span>
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
                      {EXCEPTION_LABELS[row.exception_type] ?? row.exception_type}
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
  description = "Open an invoice and match it after its purchase order and goods receipt are saved. A match is not listed here. This list shows problems that were found.",
  emptyTitle = "No problems recorded",
  emptyDescription = "Nothing on this list yet. A clean match is not listed here.",
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
