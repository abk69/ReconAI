"""PDF policy source parsing — reuses M4 PyMuPDF extraction."""

from __future__ import annotations

import re
from uuid import uuid4

from app.extraction.pdf import PDFExtractor
from app.policy.markdown import parse_markdown
from app.policy.schemas import ContentBlock, ParsedSection, ParsedSource

_HEADING_LIKE = re.compile(
    r"^(?:#{1,6}\s+)?(\d+(?:\.\d+)*)?\s*([A-Z][A-Za-z0-9 ,/\-]{2,80})$"
)


class PolicyPdfError(Exception):
    """PDF policy source could not be extracted."""


def parse_pdf(data: bytes, *, source_filename: str | None = None) -> ParsedSource:
    """Extract PDF text with page provenance, then structure into sections.

    Uses ``PDFExtractor`` (M4). Each page is processed for heading-like lines;
    blocks retain ``page_number``. Empty/unextractable PDFs raise ``PolicyPdfError``.
    """
    extracted = PDFExtractor().extract(
        document_id=uuid4(),
        data=data,
        filename=source_filename or "policy.pdf",
        mime_type="application/pdf",
    )
    if not extracted.full_text.strip():
        detail = "; ".join(extracted.warnings) if extracted.warnings else "no extractable text"
        raise PolicyPdfError(f"PDF contained no extractable text ({detail}).")

    sections: list[ParsedSection] = []
    for page_num, page_text in enumerate(extracted.pages, start=1):
        if not page_text.strip():
            continue
        page_sections = _sections_from_page(page_text, page_number=page_num)
        sections.extend(page_sections)

    if not sections:
        # Fallback: treat full document as one body section.
        sections.append(
            ParsedSection(
                section_id="body",
                section_title=None,
                level=0,
                blocks=[ContentBlock(text=extracted.full_text.strip(), page_number=1)],
                page_number=1,
            )
        )

    return ParsedSource(
        sections=sections,
        source_filename=source_filename,
        full_text=extracted.full_text,
        warnings=list(extracted.warnings),
    )


def _sections_from_page(page_text: str, *, page_number: int) -> list[ParsedSection]:
    """Structure a single PDF page; prefer Markdown-like headings when present."""
    if re.search(r"^#{1,6}\s+", page_text, flags=re.MULTILINE):
        parsed = parse_markdown(page_text, source_filename=None)
        for section in parsed.sections:
            section.page_number = page_number
            for block in section.blocks:
                block.page_number = page_number
        return parsed.sections

    lines = page_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[ParsedSection] = []
    current = ParsedSection(
        section_id=f"page-{page_number}",
        section_title=f"Page {page_number}",
        level=1,
        blocks=[],
        page_number=page_number,
    )
    buffer: list[str] = []

    def flush_block() -> None:
        nonlocal buffer
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        buffer = []
        if text:
            current.blocks.append(ContentBlock(text=text, page_number=page_number))

    def flush_section() -> None:
        flush_block()
        if current.blocks:
            sections.append(current)

    for raw in lines:
        line = raw.rstrip()
        heading = _HEADING_LIKE.match(line.strip())
        # Treat short title-case / numbered lines as headings when alone-ish.
        if heading and len(line.strip()) <= 80 and not line.strip().endswith("."):
            flush_section()
            num, title_rest = heading.group(1), heading.group(2).strip()
            title = f"{num} {title_rest}".strip() if num else title_rest
            section_id = num or f"page-{page_number}-{len(sections)}"
            current = ParsedSection(
                section_id=section_id,
                section_title=title,
                level=2 if num and "." in num else 1,
                blocks=[],
                page_number=page_number,
            )
            continue
        if not line.strip():
            flush_block()
            continue
        buffer.append(line)

    flush_section()
    if not sections and page_text.strip():
        sections.append(
            ParsedSection(
                section_id=f"page-{page_number}",
                section_title=f"Page {page_number}",
                level=1,
                blocks=[ContentBlock(text=page_text.strip(), page_number=page_number)],
                page_number=page_number,
            )
        )
    return sections
