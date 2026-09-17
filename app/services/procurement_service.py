"""Structured procurement record intake (no document extraction)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)
from app.domain.enums import (
    GoodsReceiptStatus,
    InvoiceStatus,
    PurchaseOrderStatus,
)


class ProcurementServiceError(Exception):
    """Base procurement service error."""


class ProcurementNotFoundError(ProcurementServiceError):
    """Raised when a referenced entity does not exist."""


class ProcurementValidationError(ProcurementServiceError):
    """Raised when business validation fails."""


class ProcurementService:
    """Create and fetch vendors, POs, GRNs, and invoices."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- Vendors --------------------------------------------------------------

    def create_vendor(self, *, name: str, tax_id: str | None = None) -> Vendor:
        vendor = Vendor(name=name, tax_id=tax_id)
        self._session.add(vendor)
        self._session.commit()
        return vendor

    def get_vendor(self, vendor_id: UUID) -> Vendor:
        vendor = self._session.get(Vendor, vendor_id)
        if vendor is None:
            raise ProcurementNotFoundError(f"Vendor {vendor_id} was not found.")
        return vendor

    # --- Purchase orders ------------------------------------------------------

    def create_purchase_order(
        self,
        *,
        po_number: str,
        vendor_id: UUID,
        order_date: date,
        currency: str = "USD",
        status: PurchaseOrderStatus = PurchaseOrderStatus.OPEN,
        lines: list[dict[str, object]] | None = None,
    ) -> PurchaseOrder:
        if self._session.get(Vendor, vendor_id) is None:
            raise ProcurementNotFoundError(f"Vendor {vendor_id} was not found.")

        po = PurchaseOrder(
            po_number=po_number,
            vendor_id=vendor_id,
            order_date=order_date,
            currency=currency,
            status=status.value,
        )
        for line in lines or []:
            po.lines.append(
                PurchaseOrderLine(
                    line_number=int(line["line_number"]),  # type: ignore[arg-type]
                    description=line.get("description"),  # type: ignore[arg-type]
                    quantity=Decimal(str(line["quantity"])),
                    unit_price=Decimal(str(line["unit_price"])),
                    tax_rate=Decimal(str(line.get("tax_rate", "0"))),
                )
            )
        self._session.add(po)
        self._session.commit()
        return self.get_purchase_order(po.id)

    def get_purchase_order(self, purchase_order_id: UUID) -> PurchaseOrder:
        po = self._session.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == purchase_order_id)
            .options(selectinload(PurchaseOrder.lines))
        )
        if po is None:
            raise ProcurementNotFoundError(f"Purchase order {purchase_order_id} was not found.")
        return po

    # --- Goods receipts -------------------------------------------------------

    def create_goods_receipt(
        self,
        *,
        grn_number: str,
        purchase_order_id: UUID,
        receipt_date: date,
        status: GoodsReceiptStatus = GoodsReceiptStatus.POSTED,
        lines: list[dict[str, object]] | None = None,
    ) -> GoodsReceipt:
        po = self.get_purchase_order(purchase_order_id)
        po_line_ids = {line.id for line in po.lines}

        grn = GoodsReceipt(
            grn_number=grn_number,
            purchase_order_id=purchase_order_id,
            receipt_date=receipt_date,
            status=status.value,
        )
        for line in lines or []:
            po_line_id = line.get("purchase_order_line_id")
            if po_line_id is not None:
                po_line_uuid = UUID(str(po_line_id))
                if po_line_uuid not in po_line_ids:
                    raise ProcurementValidationError(
                        f"Purchase order line {po_line_uuid} does not belong to "
                        f"purchase order {purchase_order_id}."
                    )
            else:
                po_line_uuid = None
            grn.lines.append(
                GoodsReceiptLine(
                    line_number=int(line["line_number"]),  # type: ignore[arg-type]
                    received_quantity=Decimal(str(line["received_quantity"])),
                    purchase_order_line_id=po_line_uuid,
                )
            )
        self._session.add(grn)
        self._session.commit()
        return self.get_goods_receipt(grn.id)

    def get_goods_receipt(self, goods_receipt_id: UUID) -> GoodsReceipt:
        grn = self._session.scalar(
            select(GoodsReceipt)
            .where(GoodsReceipt.id == goods_receipt_id)
            .options(selectinload(GoodsReceipt.lines))
        )
        if grn is None:
            raise ProcurementNotFoundError(f"Goods receipt {goods_receipt_id} was not found.")
        return grn

    # --- Invoices -------------------------------------------------------------

    def create_invoice(
        self,
        *,
        invoice_number: str,
        vendor_id: UUID,
        invoice_date: date,
        currency: str = "USD",
        status: InvoiceStatus = InvoiceStatus.RECEIVED,
        purchase_order_id: UUID | None = None,
        subtotal: Decimal = Decimal("0"),
        tax_amount: Decimal = Decimal("0"),
        total_amount: Decimal = Decimal("0"),
        lines: list[dict[str, object]] | None = None,
    ) -> Invoice:
        if self._session.get(Vendor, vendor_id) is None:
            raise ProcurementNotFoundError(f"Vendor {vendor_id} was not found.")

        po_line_ids: set[UUID] = set()
        if purchase_order_id is not None:
            po = self.get_purchase_order(purchase_order_id)
            po_line_ids = {line.id for line in po.lines}

        invoice = Invoice(
            invoice_number=invoice_number,
            vendor_id=vendor_id,
            purchase_order_id=purchase_order_id,
            invoice_date=invoice_date,
            currency=currency,
            status=status.value,
            subtotal=subtotal,
            tax_amount=tax_amount,
            total_amount=total_amount,
        )
        for line in lines or []:
            po_line_id = line.get("purchase_order_line_id")
            if po_line_id is not None:
                po_line_uuid = UUID(str(po_line_id))
                if purchase_order_id is None or po_line_uuid not in po_line_ids:
                    raise ProcurementValidationError(
                        f"Purchase order line {po_line_uuid} is invalid for this invoice."
                    )
            else:
                po_line_uuid = None
            invoice.lines.append(
                InvoiceLine(
                    line_number=int(line["line_number"]),  # type: ignore[arg-type]
                    description=line.get("description"),  # type: ignore[arg-type]
                    quantity=Decimal(str(line["quantity"])),
                    unit_price=Decimal(str(line["unit_price"])),
                    tax_rate=Decimal(str(line.get("tax_rate", "0"))),
                    purchase_order_line_id=po_line_uuid,
                )
            )
        self._session.add(invoice)
        self._session.commit()
        return self.get_invoice(invoice.id)

    def get_invoice(self, invoice_id: UUID) -> Invoice:
        invoice = self._session.scalar(
            select(Invoice).where(Invoice.id == invoice_id).options(selectinload(Invoice.lines))
        )
        if invoice is None:
            raise ProcurementNotFoundError(f"Invoice {invoice_id} was not found.")
        return invoice
