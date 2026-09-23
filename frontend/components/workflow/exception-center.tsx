"use client";

import Link from "next/link";

import { EvidencePanel } from "@/components/procurement/evidence";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { EnumBadge } from "@/components/ui/enum-badge";
import { getException } from "@/lib/api/procurement";
import { listPolicyGrounding, listResolutionPlans } from "@/lib/api/workflow";
import { formatTimestamp, readableLabel } from "@/lib/labels";
import type { PolicyCitation } from "@/types/workflow";

function CitationList({ citations }: { citations: PolicyCitation[] }) {
  if (citations.length === 0) {
    return <p className="text-sm text-ink-muted">No policy citations were stored.</p>;
  }
  return (
    <ul className="space-y-3">
      {citations.map((citation, index) => {
        if (!citation || typeof citation !== "object") {
          return (
            <li key={index} className="text-sm">
              {String(citation)}
            </li>
          );
        }
        return (
          <li key={`${citation.chunk_id ?? "citation"}-${index}`} className="text-sm leading-6">
            <p className="font-medium text-ink">
              {citation.section_title || citation.policy_version_label || "Stored citation"}
            </p>
            <p className="text-ink-muted">
              {[
                citation.source_filename,
                citation.page_number != null ? `page ${citation.page_number}` : null,
                citation.policy_version_label ? `version ${citation.policy_version_label}` : null,
                citation.chunk_id ? `chunk ${citation.chunk_id}` : null,
              ]
                .filter(Boolean)
                .join(" · ") || "Provenance fields were not stored on this citation."}
            </p>
          </li>
        );
      })}
    </ul>
  );
}

export function ExceptionCenterDetail({ id }: { id: string }) {
  const exception = useResource(id, (signal) => getException(id, signal), "Exception");
  const grounding = useResource(
    `${id}:grounding`,
    (signal) => listPolicyGrounding(id, signal),
    "Policy grounding",
  );
  const plans = useResource(
    `${id}:plans`,
    (signal) => listResolutionPlans({ reconciliation_exception_id: id, limit: 25 }, signal),
    "Resolution plans",
  );

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={exception} loadingTitle="Loading exception" empty={null}>
        {(item) => (
          <>
            <div>
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">
                Reconciliation fact
              </p>
              <h1 className="mt-1 text-2xl font-semibold text-ink">{readableLabel(item.exception_type)}</h1>
              <p className="mt-1 text-xs text-ink-muted">{item.exception_type}</p>
              <p className="mt-3 text-sm leading-6 text-ink">{item.message}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <EnumBadge value={item.severity} kind="severity" />
                <EnumBadge value={item.status} kind="status" />
              </div>
            </div>

            <section className="rounded-md border border-line bg-surface p-5">
              <h2 className="text-base font-semibold">Exception identity</h2>
              <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <div>
                  <dt className="text-xs uppercase text-ink-muted">Record</dt>
                  <dd className="mt-1 break-all">{item.id}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-ink-muted">Created</dt>
                  <dd className="mt-1">{formatTimestamp(item.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-ink-muted">Review state</dt>
                  <dd className="mt-1">
                    {item.status === "OPEN"
                      ? "Open. No resolution is implied."
                      : item.status === "IN_REVIEW"
                        ? "In review. A person still has to authorize any action."
                        : readableLabel(item.status)}
                  </dd>
                </div>
                <div>
                  <dt className="text-xs uppercase text-ink-muted">Resolved at</dt>
                  <dd className="mt-1">{item.resolved_at ? formatTimestamp(item.resolved_at) : "Not resolved"}</dd>
                </div>
              </dl>
            </section>

            <EvidencePanel evidence={item.evidence} />

            <section className="rounded-md border border-line bg-surface p-5">
              <h2 className="text-base font-semibold">Source records</h2>
              <ul className="mt-3 space-y-2 text-sm">
                <li>
                  {item.invoice_id ? (
                    <Link className="text-brand underline" href={`/invoices/${item.invoice_id}`}>
                      Invoice {item.invoice_number ?? item.invoice_id}
                    </Link>
                  ) : (
                    "No invoice"
                  )}
                </li>
                <li>
                  {item.purchase_order_id ? (
                    <Link className="text-brand underline" href={`/purchase-orders/${item.purchase_order_id}`}>
                      Purchase order {item.po_number ?? item.purchase_order_id}
                    </Link>
                  ) : (
                    "No purchase order"
                  )}
                </li>
                <li>
                  {item.goods_receipt_id ? (
                    <Link className="text-brand underline" href={`/goods-receipts/${item.goods_receipt_id}`}>
                      Goods receipt {item.grn_number ?? item.goods_receipt_id}
                    </Link>
                  ) : (
                    "No goods receipt"
                  )}
                </li>
              </ul>
              <h3 className="mt-4 text-sm font-semibold">Document context</h3>
              {item.source_document_ids.length === 0 ? (
                <p className="mt-2 text-sm text-ink-muted">No source document ids were stored on this exception.</p>
              ) : (
                <ul className="mt-2 space-y-2 text-sm">
                  {item.source_document_ids.map((documentId) => (
                    <li key={documentId}>
                      <Link className="text-brand underline" href={`/documents/${documentId}`}>
                        Document {documentId}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rounded-md border border-line bg-surface p-5" aria-labelledby="grounding-heading">
              <p className="text-xs font-medium tracking-wide text-ink-muted uppercase">
                AI-assisted policy explanation
              </p>
              <h2 id="grounding-heading" className="mt-1 text-base font-semibold">
                Policy grounding
              </h2>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                This section shows a stored explanation when one exists. It is not the reconciliation
                fact, and it is not a verified decision.
              </p>
              {grounding.kind === "loading" ? <p className="mt-3 text-sm">Loading stored policy grounding.</p> : null}
              {grounding.kind === "error" ? (
                <p className="mt-3 text-sm" role="alert">
                  {grounding.message}
                </p>
              ) : null}
              {grounding.kind === "ready" && grounding.data.items.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">Policy grounding is unavailable for this exception.</p>
              ) : null}
              {grounding.kind === "ready"
                ? grounding.data.items.map((row) => (
                    <article key={row.id} className="mt-4 space-y-3 border-t border-line pt-4">
                      <EnumBadge value={row.status} kind="status" />
                      <div>
                        <h3 className="text-sm font-semibold">Conclusion</h3>
                        <p className="mt-1 text-sm leading-6">{row.conclusion}</p>
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold">Explanation</h3>
                        <p className="mt-1 text-sm leading-6">{row.explanation}</p>
                      </div>
                      {row.policy_support ? (
                        <div>
                          <h3 className="text-sm font-semibold">Policy support</h3>
                          <p className="mt-1 text-sm leading-6">{row.policy_support}</p>
                        </div>
                      ) : null}
                      <div>
                        <h3 className="text-sm font-semibold">Limitations</h3>
                        <p className="mt-1 text-sm leading-6">{row.limitations || "No limitations text was stored."}</p>
                      </div>
                      <div>
                        <h3 className="text-sm font-semibold">Citations</h3>
                        <div className="mt-2">
                          <CitationList citations={row.citations} />
                        </div>
                      </div>
                      <p className="text-xs text-ink-muted">
                        Stored {formatTimestamp(row.created_at)}
                        {row.model ? ` · model ${row.model}` : ""}
                      </p>
                    </article>
                  ))
                : null}
            </section>

            <section className="rounded-md border border-line bg-surface p-5">
              <h2 className="text-base font-semibold">Available next actions</h2>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Opening this page does not execute anything. A stored resolution plan is an AI or
                system proposal until a person approves it.
              </p>
              {plans.kind === "loading" ? <p className="mt-3 text-sm">Loading resolution plans.</p> : null}
              {plans.kind === "error" ? (
                <p className="mt-3 text-sm" role="alert">
                  {plans.message}
                </p>
              ) : null}
              {plans.kind === "ready" && plans.data.items.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">
                  No resolution plan is stored for this exception. This page does not generate one.
                </p>
              ) : null}
              {plans.kind === "ready" && plans.data.items.length > 0 ? (
                <ul className="mt-3 space-y-2 text-sm">
                  {plans.data.items.map((plan) => (
                    <li key={plan.id}>
                      <Link className="text-brand underline" href={`/resolution/${plan.id}`}>
                        AI-proposed resolution plan
                      </Link>
                      <span className="ml-2">{plan.status}</span>
                      <span className="ml-2 text-ink-muted">{plan.action_count} actions</span>
                    </li>
                  ))}
                </ul>
              ) : null}
              <p className="mt-3 text-sm">
                <Link className="text-brand underline" href={`/reconciliation/${item.id}`}>
                  Open the reconciliation record
                </Link>
              </p>
            </section>
          </>
        )}
      </RecordState>
    </div>
  );
}
