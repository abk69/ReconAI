"""Image OCR adapter — fails gracefully when Tesseract is unavailable."""

from __future__ import annotations

from uuid import UUID

from app.extraction.base import DocumentExtractor
from app.extraction.schemas import ExtractedDocument, TextBlock


class ImageExtractor(DocumentExtractor):
    """OCR images with pytesseract when available; otherwise REVIEW-oriented result."""

    name = "image_tesseract"

    def extract(
        self,
        *,
        document_id: UUID,
        data: bytes,
        filename: str,
        mime_type: str,
    ) -> ExtractedDocument:
        warnings: list[str] = []
        try:
            from io import BytesIO

            from PIL import Image
        except ImportError:
            return ExtractedDocument(
                document_id=document_id,
                extractor_name=self.name,
                warnings=["Pillow is not installed; OCR unavailable."],
                metadata={
                    "filename": filename,
                    "mime_type": mime_type,
                    "ocr_available": False,
                },
            )

        try:
            import pytesseract
        except ImportError:
            return ExtractedDocument(
                document_id=document_id,
                extractor_name=self.name,
                warnings=["pytesseract is not installed; OCR unavailable."],
                metadata={
                    "filename": filename,
                    "mime_type": mime_type,
                    "ocr_available": False,
                },
            )

        try:
            image = Image.open(BytesIO(data))
            text = pytesseract.image_to_string(image) or ""
        except Exception as exc:  # noqa: BLE001 — includes missing tesseract binary
            return ExtractedDocument(
                document_id=document_id,
                extractor_name=self.name,
                warnings=[f"OCR unavailable or failed: {exc}"],
                metadata={
                    "filename": filename,
                    "mime_type": mime_type,
                    "ocr_available": False,
                },
            )

        blocks = [TextBlock(text=text, page=1, source_type="ocr_image")] if text.strip() else []
        if not text.strip():
            warnings.append("OCR produced empty text.")

        return ExtractedDocument(
            document_id=document_id,
            pages=[text],
            text_blocks=blocks,
            full_text=text,
            extractor_name=self.name,
            warnings=warnings,
            metadata={
                "filename": filename,
                "mime_type": mime_type,
                "ocr_available": True,
                "ocr_source": "tesseract",
            },
        )
