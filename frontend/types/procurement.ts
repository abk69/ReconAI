/** Procurement workspace contracts. Monetary fields are stored backend values. */

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};

export type PurchaseOrderListItem = {
  id: string;
  po_number: string;
  vendor_id: string;
  vendor_name: string;
  order_date: string;
  currency: string;
  status: string;
  line_count: number;
  created_at: string;
};

export type PurchaseOrderLine = {
  id: string;
  line_number: number;
  description: string | null;
  quantity: string;
  unit_price: string;
  tax_rate: string;
};

export type PurchaseOrderDetail = {
  id: string;
  po_number: string;
  vendor_id: string;
  order_date: string;
  currency: string;
  status: string;
  lines: PurchaseOrderLine[];
  created_at: string;
  updated_at: string;
};

export type GoodsReceiptListItem = {
  id: string;
  grn_number: string;
  purchase_order_id: string;
  po_number: string;
  receipt_date: string;
  status: string;
  line_count: number;
  created_at: string;
};

export type GoodsReceiptLine = {
  id: string;
  line_number: number;
  received_quantity: string;
  purchase_order_line_id: string | null;
};

export type GoodsReceiptDetail = {
  id: string;
  grn_number: string;
  purchase_order_id: string;
  receipt_date: string;
  status: string;
  lines: GoodsReceiptLine[];
  created_at: string;
  updated_at: string;
};

export type InvoiceListItem = {
  id: string;
  invoice_number: string;
  vendor_id: string;
  vendor_name: string;
  purchase_order_id: string | null;
  po_number: string | null;
  invoice_date: string;
  currency: string;
  status: string;
  total_amount: string;
  line_count: number;
  created_at: string;
};

export type InvoiceLine = {
  id: string;
  line_number: number;
  description: string | null;
  quantity: string;
  unit_price: string;
  tax_rate: string;
};

export type InvoiceDetail = {
  id: string;
  invoice_number: string;
  vendor_id: string;
  purchase_order_id: string | null;
  invoice_date: string;
  currency: string;
  status: string;
  subtotal: string;
  tax_amount: string;
  total_amount: string;
  lines: InvoiceLine[];
  created_at: string;
  updated_at: string;
};

export type Vendor = {
  id: string;
  name: string;
  tax_id: string | null;
};

export type DocumentItem = {
  id: string;
  original_filename: string;
  document_type: string;
  mime_type: string;
  file_extension: string;
  file_size: number;
  sha256: string;
  status: string;
  vendor_id: string | null;
  purchase_order_id: string | null;
  goods_receipt_id: string | null;
  invoice_id: string | null;
  created_at: string;
  updated_at: string;
  detected_type?: string | null;
  extraction_outcome?: string | null;
  review_status?: string | null;
};

export type DocumentList = {
  items: DocumentItem[];
  count: number;
  total: number;
};

export type ExceptionListItem = {
  id: string;
  exception_type: string;
  severity: string;
  status: string;
  message: string;
  invoice_id: string | null;
  invoice_number: string | null;
  purchase_order_id: string | null;
  po_number: string | null;
  goods_receipt_id: string | null;
  grn_number: string | null;
  created_at: string;
};

export type ExceptionList = Page<ExceptionListItem> & {
  counts_by_status: Record<string, number>;
};

export type ExceptionDetail = ExceptionListItem & {
  source_document_ids: string[];
  evidence: Record<string, unknown>;
  resolved_at: string | null;
};
