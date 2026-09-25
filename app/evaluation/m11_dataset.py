"""Versioned synthetic extraction cases. These are not production documents."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domain.enums import DocumentType
from app.evaluation.m11_schema import (
    DATASET_ID,
    EvalCase,
    GroundTruth,
    GroundTruthLine,
    SourceTable,
)

_D = Decimal


def _case(
    case_id: str,
    document_type: DocumentType,
    source_representation: str,
    source_text: str,
    filename: str,
    ground_truth: GroundTruth,
    notes: str,
    edge_conditions: list[str],
    tables: list[SourceTable] | None = None,
) -> EvalCase:
    return EvalCase(
        case_id=case_id,
        document_type=document_type,
        source_representation=source_representation,
        source_text=source_text,
        filename=filename,
        tables=tables or [],
        ground_truth=ground_truth,
        notes=notes,
        edge_conditions=edge_conditions,
    )


DATASET: tuple[EvalCase, ...] = (
    _case(
        "clean-invoice",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-1001\nVendor: Northwind Supplies\n"
        "Invoice Date: 2026-09-15\nPO Number: PO-1001\nCurrency: USD\n"
        "Cable 10 25.00\nSubtotal: 250.00\nTax: 0.00\nTotal: 250.00\n",
        "invoice-clean.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Northwind Supplies",
            invoice_number="INV-1001",
            po_number="PO-1001",
            invoice_date=date(2026, 9, 15),
            currency="USD",
            subtotal=_D("250.00"),
            tax_amount=_D("0.00"),
            total_amount=_D("250.00"),
            lines=[
                GroundTruthLine(
                    description="Cable",
                    quantity=_D("10"),
                    unit_price=_D("25.00"),
                    line_total=_D("250.00"),
                )
            ],
        ),
        "Labelled invoice with one line.",
        ["clean_header", "single_line"],
    ),
    _case(
        "clean-purchase-order",
        DocumentType.PO,
        "pdf_text",
        "PURCHASE ORDER\nPO Number: PO-2002\nVendor: Contoso Ltd\n"
        "Order Date: 2026-07-01\nCurrency: USD\nBolt 100 1.50\n",
        "purchase-order-clean.pdf",
        GroundTruth(
            document_type=DocumentType.PO,
            vendor_name="Contoso Ltd",
            po_number="PO-2002",
            order_date=date(2026, 7, 1),
            currency="USD",
            lines=[GroundTruthLine(description="Bolt", quantity=_D("100"), unit_price=_D("1.50"))],
        ),
        "Labelled purchase order.",
        ["clean_header"],
    ),
    _case(
        "clean-goods-receipt",
        DocumentType.GRN,
        "pdf_text",
        "GOODS RECEIPT\nGRN Number: GRN-3003\nPO Number: PO-2002\n"
        "Vendor: Contoso Ltd\nReceipt Date: 2026-07-04\nBolt 100 1.50\n",
        "goods-receipt-clean.pdf",
        GroundTruth(
            document_type=DocumentType.GRN,
            vendor_name="Contoso Ltd",
            grn_number="GRN-3003",
            po_number="PO-2002",
            receipt_date=date(2026, 7, 4),
            lines=[GroundTruthLine(description="Bolt", quantity=_D("100"), unit_price=_D("1.50"))],
        ),
        "Labelled goods receipt.",
        ["clean_header"],
    ),
    _case(
        "decimal-quantities",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-4004\nVendor: Fabrikam\n"
        "Invoice Date: 2026-01-20\nCloth 2.5 12.40\n",
        "invoice-qty.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Fabrikam",
            invoice_number="INV-4004",
            invoice_date=date(2026, 1, 20),
            lines=[
                GroundTruthLine(description="Cloth", quantity=_D("2.5"), unit_price=_D("12.40"))
            ],
        ),
        "Quantity is a decimal.",
        ["decimal_quantity"],
    ),
    _case(
        "decimal-prices",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-4005\nVendor: Fabrikam\n"
        "Invoice Date: 2026-01-21\nWasher 3 0.75\n",
        "invoice-price.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Fabrikam",
            invoice_number="INV-4005",
            invoice_date=date(2026, 1, 21),
            lines=[GroundTruthLine(description="Washer", quantity=_D("3"), unit_price=_D("0.75"))],
        ),
        "Unit price is below 1.",
        ["decimal_price"],
    ),
    _case(
        "tax-fields",
        DocumentType.INVOICE,
        "xlsx_table",
        "TAX INVOICE\nInvoice Number: INV-5006\nVendor: Adventure Works\n"
        "Invoice Date: 2026-03-01\nCurrency: INR\nSubtotal: 1000.00\nTax: 180.00\nTotal: 1180.00\n",
        "invoice-tax.xlsx",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Adventure Works",
            invoice_number="INV-5006",
            invoice_date=date(2026, 3, 1),
            currency="INR",
            subtotal=_D("1000.00"),
            tax_amount=_D("180.00"),
            total_amount=_D("1180.00"),
            lines=[
                GroundTruthLine(
                    item_identifier="SKU-1",
                    description="Panel",
                    quantity=_D("2"),
                    unit_price=_D("500.00"),
                    tax_rate=_D("0.18"),
                    line_total=_D("1180.00"),
                )
            ],
        ),
        "Header tax and a table tax rate.",
        ["tax_header", "tax_rate"],
        tables=[
            SourceTable(
                sheet="Lines",
                headers=["Item", "Description", "Quantity", "Unit Price", "Tax"],
                rows=[["SKU-1", "Panel", "2", "500.00", "18%"]],
            )
        ],
    ),
    _case(
        "multiple-lines",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-6007\nVendor: Northwind Supplies\n"
        "Invoice Date: 2026-04-02\nCable 4 10.00\nBolt 8 1.25\n",
        "invoice-lines.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Northwind Supplies",
            invoice_number="INV-6007",
            invoice_date=date(2026, 4, 2),
            lines=[
                GroundTruthLine(description="Cable", quantity=_D("4"), unit_price=_D("10.00")),
                GroundTruthLine(description="Bolt", quantity=_D("8"), unit_price=_D("1.25")),
            ],
        ),
        "Two text lines.",
        ["multiple_lines"],
    ),
    _case(
        "missing-optional-fields",
        DocumentType.PO,
        "pdf_text",
        "PURCHASE ORDER\nPO Number: PO-7008\nVendor: Contoso Ltd\nOrder Date: 2026-05-05\n",
        "purchase-order-sparse.pdf",
        GroundTruth(
            document_type=DocumentType.PO,
            vendor_name="Contoso Ltd",
            po_number="PO-7008",
            order_date=date(2026, 5, 5),
        ),
        "Currency and lines are absent and are not expected.",
        ["optional_absent"],
    ),
    _case(
        "date-formats",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-8009\nVendor: Fabrikam\nInvoice Date: 15/09/2026\n",
        "invoice-date.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Fabrikam",
            invoice_number="INV-8009",
            invoice_date=date(2026, 9, 15),
        ),
        "Day-first date. The first number is greater than 12.",
        ["unambiguous_day_first_date"],
    ),
    _case(
        "currency-formatting",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-9010\nVendor: Northwind Supplies\n"
        "Invoice Date: 2026-06-01\nCurrency: usd\nTotal: $1,180.50\n",
        "invoice-currency.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Northwind Supplies",
            invoice_number="INV-9010",
            invoice_date=date(2026, 6, 1),
            currency="USD",
            total_amount=_D("1180.50"),
        ),
        "Currency code case and a grouped money amount.",
        ["currency_case", "thousands_separator"],
    ),
    _case(
        "whitespace-case",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-1011\nVendor:   NORTHWIND   supplies  \n"
        "Invoice Date: 2026-06-02\n",
        "invoice-space.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Northwind Supplies",
            invoice_number="INV-1011",
            invoice_date=date(2026, 6, 2),
        ),
        "Vendor spacing and case are not meaningful differences.",
        ["whitespace", "vendor_case"],
    ),
    _case(
        "duplicate-looking-identifiers",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-1001\nPO Number: INV-1001\n"
        "Vendor: Northwind Supplies\nInvoice Date: 2026-06-03\n",
        "invoice-ids.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Northwind Supplies",
            invoice_number="INV-1001",
            po_number="INV-1001",
            invoice_date=date(2026, 6, 3),
        ),
        "The same token is a different field on the invoice and the purchase order.",
        ["identifier_collision"],
    ),
    _case(
        "malformed-values",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nInvoice Number: INV-1213\nVendor: Fabrikam\n"
        "Invoice Date: not-a-date\nTotal: twelve\n",
        "invoice-bad.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Fabrikam",
            invoice_number="INV-1213",
            invoice_date=date(2026, 2, 2),
            total_amount=_D("12.00"),
        ),
        "The source date and total are not canonical values.",
        ["malformed_date", "malformed_amount"],
    ),
    _case(
        "missing-line-fields",
        DocumentType.GRN,
        "xlsx_table",
        "GOODS RECEIPT\nGRN Number: GRN-1314\nPO Number: PO-2002\n"
        "Vendor: Contoso Ltd\nReceipt Date: 2026-08-01\n",
        "goods-receipt-partial.xlsx",
        GroundTruth(
            document_type=DocumentType.GRN,
            vendor_name="Contoso Ltd",
            grn_number="GRN-1314",
            po_number="PO-2002",
            receipt_date=date(2026, 8, 1),
            lines=[GroundTruthLine(description="Bolt", quantity=_D("4"))],
        ),
        "The line has no price. Price is not expected.",
        ["missing_line_price"],
        tables=[
            SourceTable(
                sheet="Receipt",
                headers=["Description", "Quantity"],
                rows=[["Bolt", "4"]],
            )
        ],
    ),
    _case(
        "unexpected-fields",
        DocumentType.PO,
        "pdf_text",
        "PURCHASE ORDER\nPO Number: PO-1415\nVendor: Contoso Ltd\n"
        "Order Date: 2026-08-02\nInvoice Number: SHOULD-NOT-SCORE\n",
        "purchase-order-extra.pdf",
        GroundTruth(
            document_type=DocumentType.PO,
            vendor_name="Contoso Ltd",
            po_number="PO-1415",
            order_date=date(2026, 8, 2),
        ),
        "An invoice number on a purchase order is not ground truth.",
        ["unexpected_identifier"],
    ),
    _case(
        "empty-extraction",
        DocumentType.INVOICE,
        "pdf_text",
        "\n",
        "invoice-empty.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            invoice_number="INV-1516",
            vendor_name="Northwind Supplies",
        ),
        "The source has no labelled fields.",
        ["empty_source"],
    ),
    _case(
        "noisy-text",
        DocumentType.INVOICE,
        "pdf_text",
        "TAX INVOICE\nplease ignore this banner\nInvoice Number: INV-1617\n"
        "Vendor: Northwind Supplies\nInvoice Date: 2026-08-08\n"
        "page 1 of 2 continued on next page\nCable 1 10.00\n",
        "invoice-noisy.pdf",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Northwind Supplies",
            invoice_number="INV-1617",
            invoice_date=date(2026, 8, 8),
            lines=[GroundTruthLine(description="Cable", quantity=_D("1"), unit_price=_D("10.00"))],
        ),
        "Unrelated lines surround the labelled fields.",
        ["noisy_text"],
    ),
    _case(
        "xlsx-structured",
        DocumentType.INVOICE,
        "xlsx_table",
        "TAX INVOICE\nInvoice Number: INV-1718\nVendor: Adventure Works\n"
        "Invoice Date: 2026-09-01\n",
        "invoice-sheet.xlsx",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Adventure Works",
            invoice_number="INV-1718",
            invoice_date=date(2026, 9, 1),
            lines=[
                GroundTruthLine(
                    item_identifier="A-1",
                    description="Nut",
                    quantity=_D("50"),
                    unit_price=_D("0.20"),
                ),
                GroundTruthLine(
                    item_identifier="A-2",
                    description="Washer",
                    quantity=_D("50"),
                    unit_price=_D("0.15"),
                ),
            ],
        ),
        "Lines come from a table rather than prose.",
        ["xlsx_table", "item_identifier"],
        tables=[
            SourceTable(
                sheet="Lines",
                headers=["Item", "Description", "Quantity", "Unit Price"],
                rows=[["A-1", "Nut", "50", "0.20"], ["A-2", "Washer", "50", "0.15"]],
            )
        ],
    ),
    _case(
        "pdf-style-text",
        DocumentType.PO,
        "pdf_text",
        "PURCHASE ORDER\nPO Number: PO-1819\nVendor: Northwind Supplies\n"
        "Order Date: 2026-09-09\nSteel Rod 5 120.00\n",
        "purchase-order-text.pdf",
        GroundTruth(
            document_type=DocumentType.PO,
            vendor_name="Northwind Supplies",
            po_number="PO-1819",
            order_date=date(2026, 9, 9),
            lines=[
                GroundTruthLine(description="Steel Rod", quantity=_D("5"), unit_price=_D("120.00"))
            ],
        ),
        "Plain extracted text, not a rendered PDF.",
        ["pdf_text"],
    ),
    _case(
        "ocr-noisy-text",
        DocumentType.INVOICE,
        "ocr_text",
        "TAX lNVOICE\nInv0ice Number: INV-77O1\nVend0r: N0rthwind Supp1ies\n"
        "Invoice Date: 2026-09-19\nCab1e 1O 25.OO\n",
        "invoice-scan.png",
        GroundTruth(
            document_type=DocumentType.INVOICE,
            vendor_name="Northwind Supplies",
            invoice_number="INV-7701",
            invoice_date=date(2026, 9, 19),
            lines=[GroundTruthLine(description="Cable", quantity=_D("10"), unit_price=_D("25.00"))],
        ),
        "OCR substitutions are different values, not formatting.",
        ["ocr_noise"],
    ),
)


def dataset_cases() -> tuple[EvalCase, ...]:
    return DATASET


__all__ = ["DATASET", "DATASET_ID", "dataset_cases"]
