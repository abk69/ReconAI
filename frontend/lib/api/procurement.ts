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
  params: ListParams & { document_type?: string },
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
