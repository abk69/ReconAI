"""Synthetic workloads for m11_performance_eval_v1. Sizes are explicit."""

from __future__ import annotations

from dataclasses import dataclass

DATASET_ID = "m11_performance_eval_v1"
WARMUP_RUNS = 1
MEASURED_RUNS = 5


@dataclass(frozen=True)
class Workload:
    case_id: str
    operation: str
    char_count: int


def _invoice(lines: int) -> str:
    header = "Invoice INV-PERF-1\nVendor Northwind\nInvoice Date: 2026-09-01\n"
    body = "".join(
        f"Line {index} Cable qty {index} price 10.00\n" for index in range(1, lines + 1)
    )
    return header + body


SMALL_INVOICE = _invoice(1)
MEDIUM_INVOICE = _invoice(8)
LARGE_INVOICE = _invoice(40)
PURCHASE_ORDER = "Purchase Order PO-PERF-1\nVendor Northwind\nItem Cable qty 4 price 10.00\n"
GOODS_RECEIPT = "Goods Receipt GRN-PERF-1\nVendor Northwind\nItem Cable qty 4\n"
XLSX_TEXT = "Item\tQty\tPrice\nCable\t4\t10.00\nWasher\t8\t0.50\n"
OCR_TEXT = "1nvoice INV-PERF-1 Vend0r Northwind T0tal l00.00\n"

WORKLOADS: tuple[Workload, ...] = (
    Workload("small-invoice", "m4_extraction", len(SMALL_INVOICE)),
    Workload("medium-invoice", "m4_extraction", len(MEDIUM_INVOICE)),
    Workload("large-invoice", "m4_extraction", len(LARGE_INVOICE)),
    Workload("purchase-order", "m4_extraction", len(PURCHASE_ORDER)),
    Workload("goods-receipt", "m4_extraction", len(GOODS_RECEIPT)),
    Workload("xlsx-style", "m4_extraction", len(XLSX_TEXT)),
    Workload("ocr-noisy", "m4_extraction", len(OCR_TEXT)),
    Workload("m4-only", "m4_extraction", len(SMALL_INVOICE)),
    Workload("m6-extraction", "m6_extraction", len(SMALL_INVOICE)),
    Workload("policy-retrieval", "retrieval", 48),
    Workload("grounded-explanation", "grounding", 48),
    Workload("resolution-planning", "planner", 64),
    Workload("insufficient-grounding", "planner", 64),
    Workload("provider-failure", "provider", 0),
    Workload("timeout", "provider", 0),
    Workload("malformed-provider", "provider", 0),
    Workload("retryable-failure", "provider", 0),
    Workload("idempotent-request", "execution", 64),
)

TEXTS = {
    "small-invoice": SMALL_INVOICE,
    "medium-invoice": MEDIUM_INVOICE,
    "large-invoice": LARGE_INVOICE,
    "purchase-order": PURCHASE_ORDER,
    "goods-receipt": GOODS_RECEIPT,
    "xlsx-style": XLSX_TEXT,
    "ocr-noisy": OCR_TEXT,
    "m4-only": SMALL_INVOICE,
    "m6-extraction": SMALL_INVOICE,
}
