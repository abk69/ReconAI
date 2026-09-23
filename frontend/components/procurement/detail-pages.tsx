"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import { EvidencePanel } from "@/components/procurement/evidence";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { DataTable } from "@/components/ui/data-table";
import { EnumBadge } from "@/components/ui/enum-badge";
import {
  getException,
  getGoodsReceipt,
  getInvoice,
  getPurchaseOrder,
  getVendor,
  listExceptions,
  listGoodsReceipts,
  listInvoices,
} from "@/lib/api/procurement";
import { formatTimestamp } from "@/lib/labels";

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs font-medium tracking-wide text-ink-muted uppercase">{label}</dt>
      <dd className="mt-1 text-sm text-ink">{value}</dd>
    </div>
  );
}

function Related({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-md border border-line bg-surface p-5 shadow-card">
      <h2 className="text-base font-semibold text-ink">{title}</h2>
      <div className="mt-3 text-sm">{children}</div>
    </section>
  );
}

export function PurchaseOrderDetailPage({ id }: { id: string }) {
  const state = useResource(
    id,
    async (signal) => {
      const po = await getPurchaseOrder(id, signal);
      const [vendor, grns, invoices, exceptions] = await Promise.all([
        getVendor(po.vendor_id, signal),
        listGoodsReceipts({ purchase_order_id: id, limit: 25 }, signal),
        listInvoices({ purchase_order_id: id, limit: 25 }, signal),
        listExceptions({ purchase_order_id: id, limit: 25 }, signal),
      ]);
      return { po, vendor, grns, invoices, exceptions };
    },
    "Purchase order",
  );
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <RecordState state={state} loadingTitle="Loading purchase order" empty={null}>
        {({ po, vendor, grns, invoices, exceptions }) => (
          <>
            <div>
              <h1 className="text-2xl font-semibold text-ink">{po.po_number}</h1>
              <div className="mt-3">
                <EnumBadge value={po.status} kind="status" />
              </div>
            </div>
            <dl className="grid gap-4 rounded-md border border-line bg-surface p-5 sm:grid-cols-2">
              <Meta label="Vendor" value={vendor.name} />
              <Meta label="Order date" value={po.order_date} />
              <Meta label="Currency" value={po.currency} />
              <Meta label="Created" value={formatTimestamp(po.created_at)} />
            </dl>
            <section>
              <h2 className="mb-3 text-base font-semibold text-ink">Lines</h2>
              <p className="mb-3 text-sm text-ink-muted">Stored line fields. No order total is calculated here.</p>
              <DataTable
                caption="Purchase order lines"
                rowKey={(row) => row.id}
                rows={po.lines}
                columns={[
                  { key: "n", header: "Line", cell: (row) => row.line_number },
                  { key: "d", header: "Description", cell: (row) => row.description ?? "—" },
                  { key: "q", header: "Quantity", cell: (row) => row.quantity },
                  { key: "p", header: "Unit price", cell: (row) => row.unit_price },
                  { key: "t", header: "Tax rate", cell: (row) => row.tax_rate },
                ]}
              />
            </section>
            <Related title="Goods receipts">
              {grns.items.length === 0 ? "No goods receipts reference this purchase order." : (
                <ul className="space-y-1">
                  {grns.items.map((grn) => (
                    <li key={grn.id}>
                      <Link className="text-brand underline" href={`/goods-receipts/${grn.id}`}>{grn.grn_number}</Link>
                    </li>
                  ))}
                </ul>
              )}
            </Related>
            <Related title="Invoices">
              {invoices.items.length === 0 ? "No invoices reference this purchase order." : (
                <ul className="space-y-1">
                  {invoices.items.map((invoice) => (
                    <li key={invoice.id}>
                      <Link className="text-brand underline" href={`/invoices/${invoice.id}`}>{invoice.invoice_number}</Link>
                    </li>
                  ))}
                </ul>
              )}
            </Related>
            <Related title="Reconciliation exceptions">
              {exceptions.items.length === 0 ? "No persisted exceptions reference this purchase order." : (
                <ul className="space-y-1">
                  {exceptions.items.map((item) => (
                    <li key={item.id}>
                      <Link className="text-brand underline" href={`/reconciliation/${item.id}`}>{item.exception_type}</Link>
                      <span className="text-ink-muted"> · {item.status}</span>
                    </li>
                  ))}
                </ul>
              )}
            </Related>
          </>
        )}
      </RecordState>
    </div>
  );
}

export function GoodsReceiptDetailPage({ id }: { id: string }) {
  const state = useResource(id, (signal) => getGoodsReceipt(id, signal), "Goods receipt");
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={state} loadingTitle="Loading goods receipt" empty={null}>
        {(grn) => (
          <>
            <div>
              <h1 className="text-2xl font-semibold text-ink">{grn.grn_number}</h1>
              <div className="mt-3"><EnumBadge value={grn.status} kind="status" /></div>
            </div>
            <dl className="grid gap-4 rounded-md border border-line bg-surface p-5 sm:grid-cols-2">
              <Meta label="Receipt date" value={grn.receipt_date} />
              <Meta label="Created" value={formatTimestamp(grn.created_at)} />
            </dl>
            <Related title="Purchase order">
              <Link className="text-brand underline" href={`/purchase-orders/${grn.purchase_order_id}`}>
                Open purchase order
              </Link>
            </Related>
            <DataTable
              caption="Goods receipt lines"
              rowKey={(row) => row.id}
              rows={grn.lines}
              columns={[
                { key: "n", header: "Line", cell: (row) => row.line_number },
                { key: "q", header: "Received quantity", cell: (row) => row.received_quantity },
              ]}
            />
          </>
        )}
      </RecordState>
    </div>
  );
}

export function InvoiceDetailPage({ id }: { id: string }) {
  const state = useResource(
    id,
    async (signal) => {
      const invoice = await getInvoice(id, signal);
      const [vendor, exceptions] = await Promise.all([
        getVendor(invoice.vendor_id, signal),
        listExceptions({ invoice_id: id, limit: 25 }, signal),
      ]);
      return { invoice, vendor, exceptions };
    },
    "Invoice",
  );
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <RecordState state={state} loadingTitle="Loading invoice" empty={null}>
        {({ invoice, vendor, exceptions }) => (
          <>
            <div>
              <h1 className="text-2xl font-semibold text-ink">{invoice.invoice_number}</h1>
              <div className="mt-3"><EnumBadge value={invoice.status} kind="status" /></div>
              <p className="mt-3 text-sm text-ink-muted">
                Header amounts are stored on the invoice. They are not summed from lines in the browser.
              </p>
            </div>
            <dl className="grid gap-4 rounded-md border border-line bg-surface p-5 sm:grid-cols-2">
              <Meta label="Vendor" value={vendor.name} />
              <Meta label="Invoice date" value={invoice.invoice_date} />
              <Meta label="Subtotal" value={`${invoice.subtotal} ${invoice.currency}`} />
              <Meta label="Tax amount" value={`${invoice.tax_amount} ${invoice.currency}`} />
              <Meta label="Total amount" value={`${invoice.total_amount} ${invoice.currency}`} />
            </dl>
            <Related title="Purchase order">
              {invoice.purchase_order_id ? (
                <Link className="text-brand underline" href={`/purchase-orders/${invoice.purchase_order_id}`}>
                  Open purchase order
                </Link>
              ) : (
                "No purchase order is linked."
              )}
            </Related>
            <DataTable
              caption="Invoice lines"
              rowKey={(row) => row.id}
              rows={invoice.lines}
              columns={[
                { key: "n", header: "Line", cell: (row) => row.line_number },
                { key: "d", header: "Description", cell: (row) => row.description ?? "—" },
                { key: "q", header: "Quantity", cell: (row) => row.quantity },
                { key: "p", header: "Unit price", cell: (row) => row.unit_price },
                { key: "t", header: "Tax rate", cell: (row) => row.tax_rate },
              ]}
            />
            <Related title="Reconciliation exceptions">
              {exceptions.items.length === 0 ? "No persisted exceptions reference this invoice." : (
                <ul className="space-y-1">
                  {exceptions.items.map((item) => (
                    <li key={item.id}>
                      <Link className="text-brand underline" href={`/reconciliation/${item.id}`}>{item.exception_type}</Link>
                    </li>
                  ))}
                </ul>
              )}
            </Related>
          </>
        )}
      </RecordState>
    </div>
  );
}

export function ExceptionDetailPage({ id }: { id: string }) {
  const state = useResource(id, (signal) => getException(id, signal), "Reconciliation exception");
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={state} loadingTitle="Loading reconciliation exception" empty={null}>
        {(item) => (
          <>
            <div>
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">
                Deterministic reconciliation fact
              </p>
              <h1 className="mt-1 text-2xl font-semibold text-ink">{item.exception_type}</h1>
              <p className="mt-3 text-sm leading-6 text-ink">{item.message}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <EnumBadge value={item.severity} kind="severity" />
                <EnumBadge value={item.status} kind="status" />
              </div>
            </div>
            <dl className="grid gap-4 rounded-md border border-line bg-surface p-5 sm:grid-cols-2">
              <Meta label="Created" value={formatTimestamp(item.created_at)} />
              <Meta label="Resolved at" value={item.resolved_at ? formatTimestamp(item.resolved_at) : "Not resolved"} />
            </dl>
            <Related title="Related records">
              <ul className="space-y-2">
                <li>{item.invoice_id ? <Link className="text-brand underline" href={`/invoices/${item.invoice_id}`}>Invoice {item.invoice_number}</Link> : "No invoice"}</li>
                <li>{item.purchase_order_id ? <Link className="text-brand underline" href={`/purchase-orders/${item.purchase_order_id}`}>PO {item.po_number}</Link> : "No purchase order"}</li>
                <li>{item.goods_receipt_id ? <Link className="text-brand underline" href={`/goods-receipts/${item.goods_receipt_id}`}>GRN {item.grn_number}</Link> : "No goods receipt"}</li>
              </ul>
            </Related>
            <EvidencePanel evidence={item.evidence} />
          </>
        )}
      </RecordState>
    </div>
  );
}
