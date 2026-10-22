"use client";

import Link from "next/link";
import { useState } from "react";

import { StatusBadge } from "@/components/ui/status-badge";
import { ConfirmDialog } from "@/components/workflow/confirm-dialog";
import type { ReconciliationRun } from "@/lib/api/procurement";
import { documentArticle, documentGuidance, documentKind, documentSetTags } from "@/lib/documents/next-action";
import type { UnderstandingResult } from "@/types/documents";
import type { DocumentItem } from "@/types/procurement";
import type { ReviewTask } from "@/types/workflow";

export function DocumentActions({
  document,
  understanding,
  review,
  busy,
  error,
  run,
  purchaseOrderReady,
  goodsReceiptReady,
  invoiceReady,
  invoiceNumber,
  reconciliationStatus,
  relatedInvoiceSummary = null,
  ambiguitySummary = null,
  exceptionHref = null,
  onUnderstand,
  onRequestReview,
  onReconcile,
}: {
  document: DocumentItem;
  understanding: UnderstandingResult | null;
  review: ReviewTask | null;
  busy: string | null;
  error: string | null;
  run: ReconciliationRun | null;
  purchaseOrderReady: boolean;
  goodsReceiptReady: boolean;
  invoiceReady: boolean;
  invoiceNumber: string | null;
  reconciliationStatus: string | null;
  relatedInvoiceSummary?: string | null;
  ambiguitySummary?: string | null;
  exceptionHref?: string | null;
  onUnderstand: () => void;
  onRequestReview: () => void;
  onReconcile: () => void;
}) {
  const [confirmReconcile, setConfirmReconcile] = useState(false);
  const candidate = understanding?.candidate ?? null;
  const poNumber = typeof candidate?.po_number === "string" ? candidate.po_number : null;
  const guidance = documentGuidance({
    status: document.status,
    document_type: document.document_type,
    detected_type: understanding?.detected_type ?? document.detected_type,
    extraction_outcome: understanding?.outcome ?? null,
    review_status: review?.status ?? null,
    purchase_order_id: document.purchase_order_id,
    goods_receipt_id: document.goods_receipt_id,
    invoice_id: document.invoice_id,
    po_number: poNumber,
    purchase_order_ready: purchaseOrderReady,
    goods_receipt_ready: goodsReceiptReady,
    invoice_ready: invoiceReady,
    invoice_number: invoiceNumber,
    reconciliation_status: reconciliationStatus,
    related_invoice_summary: relatedInvoiceSummary,
    ambiguity_summary: ambiguitySummary,
  });
  const step = guidance.action;
  const disabled = busy !== null;
  const kind = documentKind(understanding?.detected_type ?? document.document_type);
  const tags = documentSetTags({
    status: document.status,
    document_type: document.document_type,
    detected_type: understanding?.detected_type ?? document.detected_type,
    po_number: poNumber,
    purchase_order_id: document.purchase_order_id,
    goods_receipt_id: document.goods_receipt_id,
    invoice_id: document.invoice_id,
    purchase_order_ready: purchaseOrderReady,
    goods_receipt_ready: goodsReceiptReady,
    invoice_ready: invoiceReady,
    reconciliation_status: reconciliationStatus,
    related_invoice_summary: relatedInvoiceSummary,
    ambiguity_summary: ambiguitySummary,
  });
  const matched = reconciliationStatus === "MATCHED";

  return (
    <section className="border-t border-white/8 pt-8">
      {tags.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {tags.map((tag) => (
            <StatusBadge key={tag.label} label={tag.label} tone={tag.tone} />
          ))}
        </div>
      ) : null}
      <p className="text-sm leading-6 text-ink">{guidance.sentence}</p>
      <p className="mt-1 text-sm text-ink-muted">This is {documentArticle(kind)} {kind}.</p>
      <div className="mt-3 flex flex-wrap gap-2">
        {step === "Understand document" || step === "Retry understanding" ? (
          <button
            type="button"
            className="min-h-10 rounded-md bg-brand px-3 py-2 text-sm text-on-brand disabled:opacity-60"
            disabled={disabled}
            onClick={onUnderstand}
          >
            {busy === "understand" ? "Understanding document." : step}
          </button>
        ) : null}
        {step === "Request review" ? (
          <button
            type="button"
            className="min-h-10 rounded-md bg-brand px-3 py-2 text-sm text-on-brand disabled:opacity-60"
            disabled={disabled}
            onClick={onRequestReview}
          >
            {busy === "review" ? "Requesting review." : "Request review"}
          </button>
        ) : null}
        {review && (step === "Review extraction" || step === "Promote extraction") ? (
          disabled ? (
            <button
              type="button"
              className="inline-flex min-h-10 items-center rounded-md bg-brand px-3 py-2 text-sm text-on-brand disabled:opacity-60"
              disabled
            >
              {step}
            </button>
          ) : (
            <Link
              className="inline-flex min-h-10 items-center rounded-md bg-brand px-3 py-2 text-sm text-on-brand"
              href={`/review/${review.id}`}
            >
              {step}
            </Link>
          )
        ) : null}
        {step === "Run reconciliation" ? (
          <button
            type="button"
            className="min-h-10 rounded-md bg-brand px-3 py-2 text-sm text-on-brand disabled:opacity-60"
            disabled={disabled}
            onClick={() => setConfirmReconcile(true)}
          >
            {busy === "reconcile" ? "Running reconciliation." : "Run reconciliation"}
          </button>
        ) : null}
        {matched && kind === "invoice" ? (
          <button
            type="button"
            className="min-h-10 cursor-not-allowed rounded-md border border-line px-3 py-2 text-sm text-ink-muted"
            disabled
          >
            All matched
          </button>
        ) : null}
        {step === "See the problem" ? (
          <Link
            className="inline-flex min-h-10 items-center text-sm text-brand underline"
            href={exceptionHref ?? "/exceptions"}
          >
            See the problem
          </Link>
        ) : null}
        {step === "View goods receipt" && document.goods_receipt_id ? (
          <Link
            className="inline-flex min-h-10 items-center text-sm text-brand underline"
            href={`/goods-receipts/${document.goods_receipt_id}`}
          >
            View goods receipt
          </Link>
        ) : null}
      </div>
      {error ? (
        <p role="alert" className="mt-3 text-sm leading-6">
          {error}
        </p>
      ) : null}
      {run && !matched ? (
        <div className="mt-4 space-y-2 text-sm leading-6">
          {run.status === "MATCHED" ? (
            <p>Matched.</p>
          ) : run.exceptions.length === 0 ? (
            <p>Reconciliation status {run.status}. No exception rows were returned.</p>
          ) : (
            <ul className="space-y-2">
              {run.exceptions.map((item) => (
                <li key={`${item.exception_type}-${item.message}`}>{item.message}</li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
      <ConfirmDialog
        open={confirmReconcile}
        title="Run reconciliation?"
        description="This persists the match result and any exceptions for this invoice. It does not invent missing documents."
        confirmLabel="Run reconciliation"
        busy={busy === "reconcile"}
        onCancel={() => setConfirmReconcile(false)}
        onConfirm={() => {
          setConfirmReconcile(false);
          onReconcile();
        }}
      />
    </section>
  );
}
