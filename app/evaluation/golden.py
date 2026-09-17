"""Small deterministic golden dataset for extraction evaluation."""

from __future__ import annotations

from decimal import Decimal

from app.domain.enums import DocumentType
from app.evaluation.schemas import GoldenDocument

GOLDEN_DATASET: list[GoldenDocument] = [
    GoldenDocument(
        evaluation_id="clean-invoice",
        document_type=DocumentType.INVOICE,
        description="Clean single-line invoice",
        expected={
            "invoice_number": "INV-1001",
            "po_number": "PO-1001",
            "vendor_name": "Acme Supplies",
            "invoice_date": "2026-09-15",
            "currency": "USD",
            "lines": [
                {
                    "line_number": 1,
                    "description": "Widget A",
                    "quantity": Decimal("10"),
                    "unit_price": Decimal("500.00"),
                    "tax_rate": Decimal("0"),
                }
            ],
        },
    ),
    GoldenDocument(
        evaluation_id="multi-line-invoice",
        document_type=DocumentType.INVOICE,
        description="Invoice with two line items",
        expected={
            "invoice_number": "INV-2002",
            "vendor_name": "Beta Traders",
            "invoice_date": "2026-08-01",
            "lines": [
                {
                    "line_number": 1,
                    "description": "Bolt",
                    "quantity": Decimal("100"),
                    "unit_price": Decimal("1.50"),
                },
                {
                    "line_number": 2,
                    "description": "Nut",
                    "quantity": Decimal("100"),
                    "unit_price": Decimal("0.75"),
                },
            ],
        },
    ),
    GoldenDocument(
        evaluation_id="clean-po",
        document_type=DocumentType.PO,
        description="Purchase order header and line",
        expected={
            "po_number": "PO-3003",
            "vendor_name": "Acme Supplies",
            "order_date": "2026-07-10",
            "currency": "USD",
            "lines": [
                {
                    "line_number": 1,
                    "description": "Steel Rod",
                    "quantity": Decimal("5"),
                    "unit_price": Decimal("120.00"),
                }
            ],
        },
    ),
    GoldenDocument(
        evaluation_id="partial-grn",
        document_type=DocumentType.GRN,
        description="Partial goods receipt against a PO",
        expected={
            "grn_number": "GRN-4004",
            "po_number": "PO-3003",
            "receipt_date": "2026-07-20",
            "lines": [
                {
                    "line_number": 1,
                    "description": "Steel Rod",
                    "quantity": Decimal("2"),
                }
            ],
        },
    ),
    GoldenDocument(
        evaluation_id="malformed-ambiguous",
        document_type=DocumentType.UNKNOWN,
        description="Ambiguous document with no reliable type",
        expected={},
        notes="Evaluator expects zero fields; overall_success is False when empty.",
    ),
]


def get_golden(evaluation_id: str) -> GoldenDocument:
    for item in GOLDEN_DATASET:
        if item.evaluation_id == evaluation_id:
            return item
    raise KeyError(f"Unknown golden evaluation_id: {evaluation_id}")
