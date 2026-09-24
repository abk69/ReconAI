"use client";

import Link from "next/link";

import { EvidencePanel } from "@/components/procurement/evidence";
import { RecordState } from "@/components/procurement/record-state";
import { useResource } from "@/components/procurement/use-resource";
import { EnumBadge } from "@/components/ui/enum-badge";
import { getException } from "@/lib/api/procurement";
import { getResolutionPlan, listPolicyGrounding, listResolutionPlans } from "@/lib/api/workflow";
import { formatTimestamp, readableLabel } from "@/lib/labels";
import type { PolicyCitation, ResolutionPlan } from "@/types/workflow";

function groundingNote(status: string): string {
  if (status === "INSUFFICIENT_EVIDENCE") {
    return "Insufficient policy evidence was retrieved to support a grounded explanation.";
  }
  if (status === "CONFLICTING_POLICY") {
    return "Stored status is CONFLICTING_POLICY. This page does not choose a policy version.";
  }
  if (status === "PROVIDER_ERROR") {
    return "Policy explanation could not be generated.";
  }
  if (status === "SUPPORTED") {
    return "Stored status is SUPPORTED. This is an AI-assisted policy explanation, not a policy decision.";
  }
  return `Stored grounding status ${status}.`;
}

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
              {citation.policy_document_id ? (
                <Link className="text-brand underline" href={`/policies/${citation.policy_document_id}`}>
                  Policy
                </Link>
              ) : (
                "Policy name was not stored"
              )}
              {" · "}
              {citation.policy_document_id && citation.policy_version_id ? (
                <Link
                  className="text-brand underline"
                  href={`/policies/${citation.policy_document_id}/versions/${citation.policy_version_id}`}
                >
                  Version {citation.policy_version_label ?? citation.policy_version_id}
                </Link>
              ) : (
                citation.policy_version_label ?? "Version was not stored"
              )}
              {" · "}
              {citation.source_filename ?? "source not stored"}
              {" · "}
              {citation.page_number != null ? `page ${citation.page_number}` : "page unavailable"}
              {" · "}
              {citation.chunk_id ? `chunk ${citation.chunk_id}` : "chunk not stored"}
            </p>
            {citation.excerpt || citation.content ? (
              <blockquote className="mt-2 max-h-40 overflow-auto border-l-2 border-line px-3 text-sm whitespace-pre-wrap">
                <span className="text-xs font-medium tracking-wide text-ink-muted uppercase">Policy data</span>
                <br />
                {citation.excerpt || citation.content}
              </blockquote>
            ) : (
              <p className="text-ink-muted">No excerpt was stored on this citation.</p>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function PlanSummary({ plan }: { plan: ResolutionPlan }) {
  return (
    <article className="mt-4 space-y-3 border-t border-line pt-4 text-sm">
      <p className="font-medium">AI-proposed plan · {plan.status}</p>
      <div>
        <h3 className="font-semibold">Reasoning summary</h3>
        <p className="mt-1 leading-6">{plan.reasoning_summary || "No reasoning summary was stored."}</p>
      </div>
      <div>
        <h3 className="font-semibold">Limitations</h3>
        <p className="mt-1 leading-6">{plan.limitations || "No limitations text was stored."}</p>
      </div>
      {plan.actions.length === 0 ? (
        <p className="text-ink-muted">No proposed actions were stored.</p>
      ) : (
        <ul className="space-y-3">
          {plan.actions.map((action) => (
            <li key={action.id} className="rounded-md border border-line p-3">
              <p className="font-medium">{action.action_type}</p>
              <p>Status: {action.status}</p>
              <p>Approval required: {action.requires_approval ? "yes" : "no"}</p>
              <details className="mt-2">
                <summary className="cursor-pointer text-brand">Stored parameters</summary>
                <pre className="mt-2 max-h-48 overflow-auto rounded-md bg-canvas p-3 text-xs">
                  {JSON.stringify(action.parameters, null, 2)}
                </pre>
              </details>
            </li>
          ))}
        </ul>
      )}
      <Link className="text-brand underline" href={`/resolution/${plan.id}`}>
        View resolution plan
      </Link>
    </article>
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
    async (signal) => {
      const list = await listResolutionPlans(
        { reconciliation_exception_id: id, limit: 10 },
        signal,
      );
      return Promise.all(list.items.map((plan) => getResolutionPlan(plan.id, signal)));
    },
    "Resolution plans",
  );

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <RecordState state={exception} loadingTitle="Loading exception" empty={null}>
        {(item) => (
          <>
            <div>
              <p className="text-[11px] font-medium tracking-[0.18em] text-ink-faint uppercase">
                Exception / {item.id.slice(0, 8)}
              </p>
              <h1 className="mt-3 text-4xl font-semibold tracking-tight text-ink">{readableLabel(item.exception_type)}</h1>
              <div className="mt-4 flex flex-wrap gap-2">
                <EnumBadge value={item.severity} kind="severity" />
                <EnumBadge value={item.status} kind="status" />
              </div>
              <p className="mt-5 max-w-3xl text-lg leading-8 text-ink">{item.message}</p>
            </div>
            <ol className="flex flex-wrap gap-x-4 gap-y-2 text-[11px] tracking-[0.14em] text-ink-faint uppercase">
              {["Fact", "Evidence", "Policy", "AI interpretation", "Human action"].map((step, index) => (
                <li key={step}>
                  {String(index + 1).padStart(2, "0")} {step}
                </li>
              ))}
            </ol>
            <p className="text-sm leading-6 text-ink-muted">
              Reconciliation establishes the fact. Policy evidence and the explanation are
              AI-assisted context. A proposed plan is not an action until a person approves it in
              the resolution workflow.
            </p>

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

            <section className="surface-ai rounded-md border border-line bg-surface p-5" aria-labelledby="grounding-heading">
              <p className="text-xs font-medium tracking-wide text-brand uppercase">
                ✦ AI-assisted policy explanation
              </p>
              <h2 id="grounding-heading" className="mt-1 text-base font-semibold">
                Policy intelligence
              </h2>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                AI-assisted policy explanation from stored results. It is not a policy decision and
                not the reconciliation fact. Opening this page does not generate a new explanation.
              </p>
              {grounding.kind === "loading" ? <p className="mt-3 text-sm">Loading stored policy grounding.</p> : null}
              {grounding.kind === "error" ? (
                <p className="mt-3 text-sm" role="alert">
                  {grounding.message}
                </p>
              ) : null}
              {grounding.kind === "ready" && grounding.data.items.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">No policy grounding is stored for this exception.</p>
              ) : null}
              {grounding.kind === "ready"
                ? grounding.data.items.map((row) => (
                    <article key={row.id} className="mt-4 space-y-3 border-t border-line pt-4">
                      <p className="text-sm font-medium">Status: {row.status}</p>
                      <EnumBadge value={row.status} kind="status" />
                      <p className="text-sm leading-6">{groundingNote(row.status)}</p>
                      {row.status === "CONFLICTING_POLICY" ? (
                        <div>
                          <h3 className="text-sm font-semibold">Relevant stored versions</h3>
                          <ul className="mt-1 space-y-1">
                            {Array.from(
                              new Map(
                                row.citations
                                  .filter((citation) => citation.policy_version_id)
                                  .map((citation) => [citation.policy_version_id, citation]),
                              ).values(),
                            ).map((citation) => (
                              <li key={citation.policy_version_id}>
                                {citation.policy_document_id && citation.policy_version_id ? (
                                  <Link
                                    className="text-brand underline"
                                    href={`/policies/${citation.policy_document_id}/versions/${citation.policy_version_id}`}
                                  >
                                    {citation.policy_version_label ?? citation.policy_version_id}
                                  </Link>
                                ) : (
                                  citation.policy_version_label ?? "Version label was not stored"
                                )}
                              </li>
                            ))}
                          </ul>
                          {row.citations.length === 0 ? (
                            <p className="text-sm text-ink-muted">No citations were stored with this conflict.</p>
                          ) : null}
                        </div>
                      ) : null}
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

            <section className="surface-ai rounded-md border border-line bg-surface p-5">
              <p className="text-xs font-medium tracking-wide text-brand uppercase">
                ✦ AI-proposed resolution plan
              </p>
              <h2 className="mt-1 text-base font-semibold">Proposed resolution</h2>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Opening this page does not generate, approve, or execute a plan. Approval stays in
                the resolution workflow.
              </p>
              {plans.kind === "loading" ? <p className="mt-3 text-sm">Loading resolution plans.</p> : null}
              {plans.kind === "error" ? (
                <p className="mt-3 text-sm" role="alert">
                  {plans.message}
                </p>
              ) : null}
              {plans.kind === "ready" && plans.data.length === 0 ? (
                <p className="mt-3 text-sm text-ink-muted">
                  No resolution plan is stored for this exception. This page does not generate one.
                </p>
              ) : null}
              {plans.kind === "ready"
                ? plans.data.map((plan) => <PlanSummary key={plan.id} plan={plan} />)
                : null}
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
