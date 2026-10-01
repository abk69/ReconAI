/** One next step for a stored document. The sentence is what a new user should read. */

export type DocumentAction =
  | "Understand document"
  | "Retry understanding"
  | "Request review"
  | "Review extraction"
  | "Promote extraction"
  | "Run reconciliation"
  | "See the problem"
  | "View goods receipt";

export type DocumentGuidance = {
  sentence: string;
  action: DocumentAction | null;
};

export type DocumentStepInput = {
  status: string;
  document_type?: string | null;
  detected_type?: string | null;
  extraction_outcome?: string | null;
  review_status?: string | null;
  purchase_order_id?: string | null;
  goods_receipt_id?: string | null;
  invoice_id?: string | null;
  po_number?: string | null;
  purchase_order_ready?: boolean;
  goods_receipt_ready?: boolean;
  invoice_ready?: boolean;
  invoice_number?: string | null;
  reconciliation_status?: string | null;
  related_invoice_summary?: string | null;
  ambiguity_summary?: string | null;
};

function documentType(row: DocumentStepInput): string | null | undefined {
  return row.detected_type || row.document_type;
}

function missingPurchaseOrder(row: DocumentStepInput): boolean {
  return (
    documentType(row) === "INVOICE" &&
    Boolean(row.extraction_outcome) &&
    row.extraction_outcome !== "REVIEW_REQUIRED" &&
    row.status !== "REVIEW_REQUIRED" &&
    !row.po_number?.trim() &&
    !row.purchase_order_id
  );
}

export function relatedInvoiceSummary(
  invoices: { invoice_number: string; status: string }[],
): string | null {
  if (invoices.length === 0) return null;
  const ordered = [...invoices].sort((left, right) =>
    left.invoice_number.localeCompare(right.invoice_number),
  );
  const matched = ordered.filter((invoice) => invoice.status === "MATCHED").length;
  const problems = ordered.filter((invoice) => invoice.status === "EXCEPTION").length;
  const pending = ordered.length - matched - problems;
  const parts: string[] = [];
  if (matched) parts.push(matched === 1 ? "1 matched" : `${matched} matched`);
  if (problems) parts.push(problems === 1 ? "1 with a problem" : `${problems} with problems`);
  if (pending) parts.push(pending === 1 ? "1 not matched yet" : `${pending} not matched yet`);
  const noun = ordered.length === 1 ? "invoice" : "invoices";
  return `${ordered.length} related ${noun} — ${parts.join(", ")}`;
}

export function invoiceStatusWords(status: string): string {
  if (status === "MATCHED") return "Matched";
  if (status === "EXCEPTION") return "Problem found";
  return "Not matched yet";
}

export type DocumentTag = {
  label: string;
  tone: "success" | "warning" | "neutral";
};

export function documentKind(type: string | null | undefined): string {
  if (type === "PO") return "purchase order";
  if (type === "GRN") return "goods receipt";
  if (type === "INVOICE") return "invoice";
  return "document";
}

export function documentArticle(kind: string): string {
  return /^[aeiou]/i.test(kind) ? "an" : "a";
}

export function documentSetTags(row: DocumentStepInput): DocumentTag[] {
  const kind = documentType(row);
  const inSet = kind === "PO" || kind === "GRN" || kind === "INVOICE" || Boolean(row.po_number);
  if (!inSet) return [];
  if (row.ambiguity_summary) {
    return [{ label: "Review required", tone: "warning" }];
  }
  if ((kind === "PO" || kind === "GRN") && row.related_invoice_summary) {
    return [{ label: "Related invoices", tone: "neutral" }];
  }
  if (row.reconciliation_status === "MATCHED") {
    return [{ label: "All matched", tone: "success" }];
  }
  if (row.reconciliation_status === "EXCEPTION") {
    return [{ label: "Problem found", tone: "warning" }];
  }
  const purchaseOrder = Boolean(row.purchase_order_ready || row.purchase_order_id);
  const goodsReceipt = Boolean(row.goods_receipt_ready || row.goods_receipt_id);
  const invoice = Boolean(row.invoice_ready || row.invoice_id);
  const tags: DocumentTag[] = [
    {
      label: purchaseOrder ? "Purchase order saved" : "Purchase order remaining",
      tone: purchaseOrder ? "neutral" : "warning",
    },
    {
      label: goodsReceipt ? "Goods receipt saved" : "Goods receipt remaining",
      tone: goodsReceipt ? "neutral" : "warning",
    },
    {
      label: invoice ? "Invoice saved" : "Invoice remaining",
      tone: invoice ? "neutral" : "warning",
    },
  ];
  if (purchaseOrder && goodsReceipt && invoice) {
    tags.push({ label: "Match remaining", tone: "warning" });
  }
  if (missingPurchaseOrder(row)) {
    tags.push({ label: "PO number missing", tone: "warning" });
  }
  return tags;
}

export function documentGuidance(row: DocumentStepInput): DocumentGuidance {
  const kind = documentKind(row.detected_type || row.document_type);
  const promoted = Boolean(row.purchase_order_id || row.goods_receipt_id || row.invoice_id);
  const poName = row.po_number?.trim() || "the purchase order";
  const purchaseOrderReady = Boolean(row.purchase_order_ready || row.purchase_order_id);
  const goodsReceiptReady = Boolean(row.goods_receipt_ready || row.goods_receipt_id);
  const invoiceName = row.invoice_number?.trim() || "the invoice";

  if (row.status === "EXTRACTION_FAILED" || row.extraction_outcome === "EXTRACTION_FAILED") {
    return { sentence: "This file could not be read. Try again.", action: "Retry understanding" };
  }

  const awaitingUnderstanding =
    !row.extraction_outcome &&
    (row.status === "UPLOADED" || row.status === "VALIDATED" || row.status === "VALIDATION_FAILED");
  if (awaitingUnderstanding) {
    return { sentence: `Read this ${kind} and extract its fields.`, action: "Understand document" };
  }

  if (row.extraction_outcome === "VALIDATION_FAILED") {
    if (!row.review_status) {
      return {
        sentence: "Some required fields could not be read. Start a review to correct them.",
        action: "Request review",
      };
    }
    if (row.review_status === "PENDING" || row.review_status === "IN_REVIEW") {
      return {
        sentence: "Correct the fields that failed checks. This document cannot be saved until they pass.",
        action: "Review extraction",
      };
    }
    return {
      sentence: "This extraction failed its checks and the review is already closed, so it cannot be saved.",
      action: "Review extraction",
    };
  }

  if (row.ambiguity_summary) {
    return {
      sentence: `Ambiguous fields require review. ${row.ambiguity_summary}`,
      action: row.review_status ? "Review extraction" : "Request review",
    };
  }

  if (
    row.review_status === "PENDING" ||
    row.review_status === "IN_REVIEW" ||
    row.status === "REVIEW_REQUIRED"
  ) {
    return {
      sentence: "Check the extracted lines, then approve them.",
      action: "Review extraction",
    };
  }

  if ((row.review_status === "APPROVED" || row.review_status === "CORRECTED") && !promoted) {
    const isGoodsReceipt = (row.detected_type || row.document_type) === "GRN";
    if (isGoodsReceipt && !purchaseOrderReady) {
      return {
        sentence: row.po_number?.trim()
          ? `Promote purchase order ${row.po_number.trim()} first.`
          : "This goods receipt has no purchase order number, so it cannot be saved yet.",
        action: null,
      };
    }
    if (missingPurchaseOrder(row)) {
      return {
        sentence: "PO number is missing. Saving this invoice will not link a purchase order.",
        action: "Promote extraction",
      };
    }
    return { sentence: `Save this ${kind}.`, action: "Promote extraction" };
  }

  const recordType = documentType(row);
  if ((recordType === "PO" || recordType === "GRN") && row.related_invoice_summary) {
    return { sentence: row.related_invoice_summary, action: null };
  }

  if (promoted && row.reconciliation_status === "MATCHED") {
    if (kind === "invoice") {
      return {
        sentence: `Matched. Invoice ${invoiceName} agrees with purchase order ${poName} and its goods receipt.`,
        action: null,
      };
    }
    return { sentence: `Matched with invoice ${invoiceName}.`, action: null };
  }

  if (promoted && row.reconciliation_status === "EXCEPTION") {
    return {
      sentence: "This set does not match. Open the problem to see why.",
      action: "See the problem",
    };
  }

  if (row.invoice_id) {
    if (purchaseOrderReady && goodsReceiptReady) {
      return {
        sentence: "Match this invoice to the purchase order and goods receipt.",
        action: "Run reconciliation",
      };
    }
    if (!purchaseOrderReady) {
      return { sentence: `Promote purchase order ${poName} before matching this invoice.`, action: null };
    }
    return { sentence: "Promote the goods receipt before matching this invoice.", action: null };
  }

  if (row.purchase_order_id && (row.detected_type || row.document_type) === "PO") {
    return {
      sentence: "This purchase order is saved. Promote its goods receipt and invoice before matching.",
      action: null,
    };
  }

  if (row.goods_receipt_id) {
    return { sentence: "This goods receipt is saved.", action: "View goods receipt" };
  }

  if (row.extraction_outcome && !row.review_status) {
    if (missingPurchaseOrder(row)) {
      return { sentence: "PO number is missing.", action: "Request review" };
    }
    return { sentence: "Ask for a review before saving this record.", action: "Request review" };
  }

  return { sentence: "Open this document to see its next step.", action: null };
}

/** @deprecated Use documentGuidance. Kept so older call sites can show the action label. */
export function nextDocumentStep(row: DocumentStepInput): string {
  return documentGuidance(row).action ?? documentGuidance(row).sentence;
}
