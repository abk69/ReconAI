import type { ProposedAction } from "@/types/workflow";

const SECRET_KEY = /key|secret|token|password|credential/i;

export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "Not present";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

export function redactMetadata(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => redactMetadata(item));
  }
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      output[key] = SECRET_KEY.test(key) ? "[redacted]" : redactMetadata(item);
    }
    return output;
  }
  return value;
}

export function actorLabel(actorType: string): "SYSTEM" | "LLM" | "HUMAN" | string {
  const upper = actorType.toUpperCase();
  if (upper === "SYSTEM" || upper === "LLM" || upper === "HUMAN") {
    return upper;
  }
  return actorType;
}

/** UI hint only. The backend remains the authority on whether execute succeeds. */
export function executionAllowed(action: Pick<ProposedAction, "status" | "requires_approval">): boolean {
  if (action.status === "REJECTED" || action.status === "COMPLETED" || action.status === "FAILED") {
    return false;
  }
  if (action.status === "CANCELLED" || action.status === "EXECUTING") {
    return false;
  }
  if (action.requires_approval) {
    return action.status === "APPROVED";
  }
  return action.status === "PENDING" || action.status === "APPROVED";
}

export function approvalAllowed(action: Pick<ProposedAction, "status" | "requires_approval">): boolean {
  return action.requires_approval && action.status === "PENDING";
}

export function promotedHref(entityType: string | null, entityId: string | null): string | null {
  if (!entityType || !entityId) {
    return null;
  }
  if (entityType === "INVOICE") {
    return `/invoices/${entityId}`;
  }
  if (entityType === "PO") {
    return `/purchase-orders/${entityId}`;
  }
  if (entityType === "GRN") {
    return `/goods-receipts/${entityId}`;
  }
  return null;
}

const EDITABLE = new Set([
  "invoice_number",
  "po_number",
  "grn_number",
  "vendor_name",
  "invoice_date",
  "order_date",
  "receipt_date",
  "currency",
  "total_amount",
  "quantity",
  "unit_price",
  "tax_rate",
  "subtotal",
  "tax_amount",
  "received_quantity",
  "description",
  "reference",
]);

export type CorrectionField = {
  path: string;
  label: string;
  value: string;
};

export function correctionFields(candidate: Record<string, unknown> | null): CorrectionField[] {
  if (!candidate) {
    return [];
  }
  const fields: CorrectionField[] = [];
  for (const [key, value] of Object.entries(candidate)) {
    if (key === "lines" || value === null || value === undefined) {
      continue;
    }
    if (EDITABLE.has(key) && (typeof value === "string" || typeof value === "number")) {
      fields.push({ path: key, label: key, value: String(value) });
    }
  }
  const lines = candidate.lines;
  if (Array.isArray(lines)) {
    lines.forEach((line, index) => {
      if (!line || typeof line !== "object") {
        return;
      }
      for (const [key, value] of Object.entries(line)) {
        if (!EDITABLE.has(key) || value === null || value === undefined) {
          continue;
        }
        if (typeof value === "string" || typeof value === "number") {
          fields.push({
            path: `lines[${index}].${key}`,
            label: `Line ${index + 1} ${key}`,
            value: String(value),
          });
        }
      }
    });
  }
  return fields;
}
