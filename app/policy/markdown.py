"""Deterministic Markdown structure detection for policy sources."""

from __future__ import annotations

import re

from app.policy.schemas import ContentBlock, ParsedSection, ParsedSource

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
# ``1. Purpose``, ``2.1 Terms``, ``3 Rules`` → ids ``1``, ``2.1``, ``3``
_SECTION_ID = re.compile(r"^(\d+(?:\.\d+)*)\.?(?:\s+|$)")


def parse_markdown(text: str, *, source_filename: str | None = None) -> ParsedSource:
    """Parse Markdown into heading-scoped sections with paragraph/list blocks.

    Algorithm:
    1. Walk lines top-to-bottom.
    2. ATATX headings (``#`` … ``######``) start a new section.
    3. Optional leading numeric path in the title becomes ``section_id``
       (e.g. ``## 2.1 Terms`` → id ``2.1``, title ``2.1 Terms``).
    4. Blank lines separate blocks; consecutive non-blank lines form one block
       (paragraphs and lists stay intact).
    5. Content before the first heading is a preamble section (id ``preamble``).
    """
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    sections: list[ParsedSection] = []
    current = ParsedSection(
        section_id="preamble",
        section_title="Preamble",
        level=0,
        blocks=[],
    )
    buffer: list[str] = []

    def flush_block() -> None:
        nonlocal buffer
        if not buffer:
            return
        block_text = "\n".join(buffer).strip()
        buffer = []
        if block_text:
            current.blocks.append(ContentBlock(text=block_text))

    def flush_section() -> None:
        flush_block()
        # Drop empty preamble / empty heading shells (nested content lives under child headings).
        if current.blocks:
            sections.append(current)

    for line in lines:
        heading = _HEADING.match(line)
        if heading:
            flush_section()
            level = len(heading.group(1))
            title = heading.group(2).strip()
            section_id = _extract_section_id(title)
            current = ParsedSection(
                section_id=section_id,
                section_title=title,
                level=level,
                blocks=[],
            )
            continue
        if not line.strip():
            flush_block()
            continue
        buffer.append(line.rstrip())

    flush_section()

    if not sections:
        # Entire document as a single section.
        body = text.strip()
        if body:
            sections.append(
                ParsedSection(
                    section_id="body",
                    section_title=None,
                    level=0,
                    blocks=[ContentBlock(text=body)],
                )
            )

    return ParsedSource(
        sections=sections,
        source_filename=source_filename,
        full_text=text,
    )


def _extract_section_id(title: str) -> str | None:
    match = _SECTION_ID.match(title)
    if match:
        return match.group(1)
    # Stable slug-like fallback from title words (deterministic, short).
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip()).strip("-").lower()
    return cleaned[:64] if cleaned else None
