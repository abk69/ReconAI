"use client";

import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { FilterBar, useListQuery } from "@/components/procurement/filters";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable, Pager } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import { LoadingState } from "@/components/ui/state";
import { listGoodsReceipts, listInvoices, listPurchaseOrders } from "@/lib/api/procurement";
import { formatTimestamp } from "@/lib/labels";

const LIMIT = 25;

function Shell({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-6xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">{description}</p>
      </div>
      {children}
    </div>
  );
}

function PurchaseOrdersBody() {
  const query = useListQuery();
  const key = `po:${query.q}:${query.status}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listPurchaseOrders({ q: query.q, status: query.status, limit: LIMIT, offset: query.offset }, signal),
    "Purchase orders",
  );
  return (
    <Shell
      title="Purchase orders"
      description="Persisted purchase orders. Line counts come from the API. This page does not total line amounts."
    >
      <FilterBar
        fields={[
          { name: "q", label: "PO number" },
          {
            name: "status",
            label: "Status",
            options: ["DRAFT", "OPEN", "PARTIALLY_RECEIVED", "CLOSED", "CANCELLED"],
          },
        ]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading purchase orders"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? { title: "No purchase orders recorded", description: "No purchase orders match this filter." }
            : null
        }
      >
        {(data) => (
          <div className="space-y-3">
            <DataTable
              caption="Purchase orders"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "po",
                  header: "PO number",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/purchase-orders/${row.id}`}>
                      {row.po_number}
                    </Link>
                  ),
                },
                { key: "vendor", header: "Vendor", cell: (row) => row.vendor_name },
                { key: "date", header: "Order date", cell: (row) => row.order_date },
                { key: "status", header: "Status", cell: (row) => <EnumBadge value={row.status} kind="status" /> },
                { key: "lines", header: "Lines", cell: (row) => row.line_count },
                { key: "created", header: "Created", cell: (row) => formatTimestamp(row.created_at) },
              ]}
            />
            <Pager offset={query.offset} limit={LIMIT} total={data.total} onPage={query.setOffset} />
          </div>
        )}
      </RecordState>
    </Shell>
  );
}

function GoodsReceiptsBody() {
  const query = useListQuery();
  const key = `grn:${query.q}:${query.status}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listGoodsReceipts({ q: query.q, status: query.status, limit: LIMIT, offset: query.offset }, signal),
    "Goods receipts",
  );
  return (
    <Shell
      title="Goods receipts"
      description="Persisted goods receipts and the purchase order each one references."
    >
      <FilterBar
        fields={[
          { name: "q", label: "GRN number" },
          { name: "status", label: "Status", options: ["DRAFT", "POSTED", "CANCELLED"] },
        ]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading goods receipts"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? { title: "No goods receipts recorded", description: "No goods receipts match this filter." }
            : null
        }
      >
        {(data) => (
          <div className="space-y-3">
            <DataTable
              caption="Goods receipts"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "grn",
                  header: "GRN number",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/goods-receipts/${row.id}`}>
                      {row.grn_number}
                    </Link>
                  ),
                },
                {
                  key: "po",
                  header: "Purchase order",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/purchase-orders/${row.purchase_order_id}`}>
                      {row.po_number}
                    </Link>
                  ),
                },
                { key: "date", header: "Receipt date", cell: (row) => row.receipt_date },
                { key: "status", header: "Status", cell: (row) => <EnumBadge value={row.status} kind="status" /> },
                { key: "lines", header: "Lines", cell: (row) => row.line_count },
              ]}
            />
            <Pager offset={query.offset} limit={LIMIT} total={data.total} onPage={query.setOffset} />
          </div>
        )}
      </RecordState>
    </Shell>
  );
}

function InvoicesBody() {
  const query = useListQuery();
  const key = `inv:${query.q}:${query.status}:${query.offset}`;
  const state = useResource(
    key,
    (signal) =>
      listInvoices({ q: query.q, status: query.status, limit: LIMIT, offset: query.offset }, signal),
    "Invoices",
  );
  return (
    <Shell
      title="Invoices"
      description="Persisted invoices. The amount column is the stored header total, not a sum calculated in the browser."
    >
      <FilterBar
        fields={[
          { name: "q", label: "Invoice number" },
          {
            name: "status",
            label: "Status",
            options: ["DRAFT", "RECEIVED", "MATCHED", "EXCEPTION", "APPROVED", "REJECTED", "CANCELLED"],
          },
        ]}
      />
      <RecordState
        state={state}
        loadingTitle="Loading invoices"
        empty={
          state.kind === "ready" && state.data.total === 0
            ? { title: "No invoices recorded", description: "No invoices match this filter." }
            : null
        }
      >
        {(data) => (
          <div className="space-y-3">
            <DataTable
              caption="Invoices"
              rowKey={(row) => row.id}
              rows={data.items}
              columns={[
                {
                  key: "number",
                  header: "Invoice",
                  cell: (row) => (
                    <Link className="text-brand underline" href={`/invoices/${row.id}`}>
                      {row.invoice_number}
                    </Link>
                  ),
                },
                { key: "vendor", header: "Vendor", cell: (row) => row.vendor_name },
                {
                  key: "po",
                  header: "Purchase order",
                  cell: (row) =>
                    row.purchase_order_id && row.po_number ? (
                      <Link className="text-brand underline" href={`/purchase-orders/${row.purchase_order_id}`}>
                        {row.po_number}
                      </Link>
                    ) : (
                      "None linked"
                    ),
                },
                { key: "date", header: "Invoice date", cell: (row) => row.invoice_date },
                { key: "status", header: "Status", cell: (row) => <EnumBadge value={row.status} kind="status" /> },
                {
                  key: "total",
                  header: "Stored total",
                  cell: (row) => `${row.total_amount} ${row.currency}`,
                },
              ]}
            />
            <Pager offset={query.offset} limit={LIMIT} total={data.total} onPage={query.setOffset} />
          </div>
        )}
      </RecordState>
    </Shell>
  );
}

function wrap(node: ReactNode, title: string) {
  return (
    <Suspense fallback={<LoadingState title={title} description="Preparing filters." />}>{node}</Suspense>
  );
}

export function PurchaseOrdersPage() {
  return wrap(<PurchaseOrdersBody />, "Loading purchase orders");
}

export function GoodsReceiptsPage() {
  return wrap(<GoodsReceiptsBody />, "Loading goods receipts");
}

export function InvoicesPage() {
  return wrap(<InvoicesBody />, "Loading invoices");
}
