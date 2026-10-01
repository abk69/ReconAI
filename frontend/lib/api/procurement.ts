import { apiRequest } from "@/lib/api/client";
import { withQuery } from "@/lib/api/query";
import type {
  DocumentItem,
  DocumentList,
  ExceptionDetail,
  ExceptionList,
  GoodsReceiptDetail,
  GoodsReceiptListItem,
  InvoiceDetail,
  InvoiceListItem,
  Page,
  PurchaseOrderDetail,
  PurchaseOrderListItem,
  Vendor,
} from "@/types/procurement";

type ListParams = {
  q?: string;
  status?: string;
  limit?: number;
  offset?: number;
};

export function listDocuments(
  params: ListParams & {
    document_type?: string;
    extraction_outcome?: string;
    review_status?: string;
  },
  signal?: AbortSignal,
): Promise<DocumentList> {
  return apiRequest(withQuery("/documents", params), { signal });
}

export function getDocument(id: string, signal?: AbortSignal): Promise<DocumentItem> {
  return apiRequest(`/documents/${id}`, { signal });
}

export function listPurchaseOrders(
  params: ListParams & { vendor_id?: string },
  signal?: AbortSignal,
): Promise<Page<PurchaseOrderListItem>> {
  return apiRequest(withQuery("/purchase-orders", params), { signal });
}

export function getPurchaseOrder(id: string, signal?: AbortSignal): Promise<PurchaseOrderDetail> {
  return apiRequest(`/purchase-orders/${id}`, { signal });
}

export function listGoodsReceipts(
  params: ListParams & { purchase_order_id?: string },
  signal?: AbortSignal,
): Promise<Page<GoodsReceiptListItem>> {
  return apiRequest(withQuery("/goods-receipts", params), { signal });
}

export function getGoodsReceipt(id: string, signal?: AbortSignal): Promise<GoodsReceiptDetail> {
  return apiRequest(`/goods-receipts/${id}`, { signal });
}

export function listInvoices(
  params: ListParams & { vendor_id?: string; purchase_order_id?: string },
  signal?: AbortSignal,
): Promise<Page<InvoiceListItem>> {
  return apiRequest(withQuery("/invoices", params), { signal });
}

export function getInvoice(id: string, signal?: AbortSignal): Promise<InvoiceDetail> {
  return apiRequest(`/invoices/${id}`, { signal });
}

export function getVendor(id: string, signal?: AbortSignal): Promise<Vendor> {
  return apiRequest(`/vendors/${id}`, { signal });
}

export type ReconciliationRun = {
  status: string;
  exception_count: number;
  exceptions: {
    exception_type: string;
    severity: string;
    message: string;
    evidence: Record<string, unknown>;
  }[];
  summary: {
    po_line_count: number;
    grn_count: number;
    invoice_line_count: number;
    total_ordered_quantity: string;
    total_received_quantity: string;
    total_invoiced_quantity: string;
  };
  purchase_order_id: string | null;
  invoice_id: string | null;
  goods_receipt_ids: string[];
};

export function runReconciliation(body: {
  purchase_order_id?: string;
  invoice_id?: string;
}): Promise<ReconciliationRun> {
  return apiRequest("/reconciliation/run", { method: "POST", body: { ...body, persist: true } });
}

export function listExceptions(
  params: ListParams & {
    severity?: string;
    exception_type?: string;
    invoice_id?: string;
    purchase_order_id?: string;
    goods_receipt_id?: string;
  },
  signal?: AbortSignal,
): Promise<ExceptionList> {
  return apiRequest(withQuery("/reconciliation/exceptions", params), { signal });
}

export function getException(id: string, signal?: AbortSignal): Promise<ExceptionDetail> {
  return apiRequest(`/reconciliation/exceptions/${id}`, { signal });
}
