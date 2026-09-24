"use client";

import Link from "next/link";

import { EvidencePanel } from "@/components/procurement/evidence";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { EnumBadge } from "@/components/ui/enum-badge";
import { getAnomaly } from "@/lib/api/risk";
import { formatTimestamp } from "@/lib/labels";

export function AnomalyDetailPage({ id }: { id: string }) {
  const state = useResource(id, (signal) => getAnomaly(id, signal), "Anomaly signal");
  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={state} loadingTitle="Loading anomaly signal" empty={null}>
        {(item) => (
          <>
            <div>
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">Anomaly</p>
              <h1 className="mt-1 text-2xl font-semibold">{item.title}</h1>
              <p className="mt-1 text-xs text-ink-muted">{item.anomaly_type}</p>
              <p className="mt-3 text-sm leading-6">{item.explanation}</p>
              <div className="mt-3">
                <EnumBadge value={item.severity} kind="severity" />
              </div>
            </div>
            <dl className="grid gap-3 border-t border-white/8 pt-6 text-sm sm:grid-cols-2">
              <div>
                <dt className="text-xs uppercase text-ink-muted">Anomaly signal score</dt>
                <dd className="mt-1">{item.score}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ink-muted">Detected</dt>
                <dd className="mt-1">{formatTimestamp(item.detected_at)}</dd>
              </div>
              <div>
                <dt className="text-xs uppercase text-ink-muted">Record identity</dt>
                <dd className="mt-1 break-all text-xs">
                  {item.fingerprint}
                  <span className="mt-1 block text-ink-muted">
                    Fingerprint is a stable identity for this stored signal.
                  </span>
                </dd>
              </div>
            </dl>
            <section className="border-t border-white/8 pt-8">
              <h2 className="text-base font-semibold">Affected records</h2>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  {item.vendor_id ? (
                    <Link className="text-brand underline" href={`/risk/vendors/${item.vendor_id}`}>
                      Vendor risk {item.vendor_id}
                    </Link>
                  ) : (
                    "No vendor"
                  )}
                </li>
                <li>
                  {item.invoice_id ? (
                    <Link className="text-brand underline" href={`/invoices/${item.invoice_id}`}>
                      Invoice {item.invoice_id}
                    </Link>
                  ) : (
                    "No invoice"
                  )}
                </li>
                <li>
                  {item.purchase_order_id ? (
                    <Link className="text-brand underline" href={`/purchase-orders/${item.purchase_order_id}`}>
                      Purchase order {item.purchase_order_id}
                    </Link>
                  ) : (
                    "No purchase order"
                  )}
                </li>
                <li>
                  {item.grn_id ? (
                    <Link className="text-brand underline" href={`/goods-receipts/${item.grn_id}`}>
                      Goods receipt {item.grn_id}
                    </Link>
                  ) : (
                    "No goods receipt"
                  )}
                </li>
              </ul>
            </section>
            <EvidencePanel
              evidence={item.evidence}
              title="Stored anomaly evidence"
              description="Fields are shown as stored by the anomaly rule. This page does not generate an explanation."
            />
          </>
        )}
      </RecordState>
    </div>
  );
}
