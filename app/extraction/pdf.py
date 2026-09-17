"""PDF text extraction via PyMuPDF with labelled field helpers."""

from __future__ import annotations

from uuid import UUID

from app.extraction.base import DocumentExtractor, find_labelled_value
from app.extraction.schemas import ExtractedDocument, TextBlock


class PDFExtractor(DocumentExtractor):
    """Extract page text from PDF bytes using PyMuPDF (fitz)."""

    name = "pdf_pymupdf"

    def extract(
        self,
        *,
        document_id: UUID,
        data: bytes,
        filename: str,
        mime_type: str,
    ) -> ExtractedDocument:
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("PyMuPDF (pymupdf) is required for PDF extraction.") from exc

        warnings: list[str] = []
        pages: list[str] = []
        blocks: list[TextBlock] = []

        try:
            doc = fitz.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001 — surface as structured warning
            return ExtractedDocument(
                document_id=document_id,
                pages=[],
                text_blocks=[],
                full_text="",
                extractor_name=self.name,
                warnings=[f"Failed to open PDF: {exc}"],
                metadata={"filename": filename, "mime_type": mime_type},
            )

        with doc:
            for index, page in enumerate(doc, start=1):
                text = page.get_text("text") or ""
                pages.append(text)
                if text.strip():
                    blocks.append(TextBlock(text=text, page=index, source_type="pdf_page"))

        full_text = "\n".join(pages)
        if not full_text.strip():
            warnings.append("PDF contained no extractable text (may be scanned).")

        # Probe labelled fields for metadata hints (classification/structure later).
        labelled: dict[str, str] = {}
        for field in (
            "invoice_number",
            "po_number",
            "grn_number",
            "vendor_name",
            "invoice_date",
            "order_date",
            "receipt_date",
        ):
            found = find_labelled_value(full_text, field)
            if found:
                labelled[field] = found[0]

        return ExtractedDocument(
            document_id=document_id,
            pages=pages,
            text_blocks=blocks,
            full_text=full_text,
            extractor_name=self.name,
            warnings=warnings,
            metadata={
                "filename": filename,
                "mime_type": mime_type,
                "page_count": len(pages),
                "labelled_fields": labelled,
            },
        )
