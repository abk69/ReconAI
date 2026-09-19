"""Section-aware deterministic policy chunking.

Algorithm
---------
1. Walk parsed sections in document order.
2. Within each section, pack consecutive blocks into a chunk while
   ``len(chunk) <= max_chars`` (joining blocks with blank lines).
3. When adding the next block would exceed ``max_chars``, close the current
   chunk and start a new one (same section metadata).
4. If a single block exceeds ``max_chars``, split on whitespace at the limit
   (never mid-word when a space exists); otherwise hard-split at ``max_chars``.
5. Assign contiguous ``chunk_index`` values from 0.
6. Hash each chunk body with SHA-256 (UTF-8).

Same input + same ``max_chars`` ⇒ identical chunks, indices, and hashes.
"""

from __future__ import annotations

from app.policy.schemas import ContentBlock, ParsedSection, ParsedSource, PreparedChunk
from app.services.policy_service import content_sha256


def chunk_sections(
    source: ParsedSource,
    *,
    max_chars: int,
) -> list[PreparedChunk]:
    """Convert parsed sections into ordered, size-bounded chunks."""
    if max_chars < 1:
        raise ValueError("max_chars must be >= 1")

    prepared: list[PreparedChunk] = []
    index = 0
    filename = source.source_filename

    for section in source.sections:
        blocks = list(section.blocks)
        if not blocks and section.joined_text.strip():
            blocks = [
                ContentBlock(text=section.joined_text.strip(), page_number=section.page_number)
            ]
        if not blocks:
            continue

        # Expand oversized blocks first.
        expanded: list[ContentBlock] = []
        for block in blocks:
            expanded.extend(_split_oversized_block(block, max_chars=max_chars))

        bucket: list[ContentBlock] = []
        bucket_len = 0
        for block in expanded:
            piece = block.text.strip()
            if not piece:
                continue
            # +2 for the blank-line joiner when bucket non-empty
            addition = len(piece) if not bucket else len(piece) + 2
            if bucket and bucket_len + addition > max_chars:
                prepared.append(
                    _to_chunk(
                        index=index,
                        section=section,
                        blocks=bucket,
                        source_filename=filename,
                    )
                )
                index += 1
                bucket = []
                bucket_len = 0
                addition = len(piece)
            bucket.append(block)
            bucket_len += addition

        if bucket:
            prepared.append(
                _to_chunk(
                    index=index,
                    section=section,
                    blocks=bucket,
                    source_filename=filename,
                )
            )
            index += 1

    return prepared


def _to_chunk(
    *,
    index: int,
    section: ParsedSection,
    blocks: list[ContentBlock],
    source_filename: str | None,
) -> PreparedChunk:
    content = "\n\n".join(b.text.strip() for b in blocks if b.text.strip())
    page = next((b.page_number for b in blocks if b.page_number is not None), section.page_number)
    return PreparedChunk(
        chunk_index=index,
        section_id=section.section_id,
        section_title=section.section_title,
        content=content,
        content_hash=content_sha256(content),
        source_filename=source_filename,
        page_number=page,
    )


def _split_oversized_block(block: ContentBlock, *, max_chars: int) -> list[ContentBlock]:
    text = block.text.strip()
    if len(text) <= max_chars:
        return [block] if text else []

    parts: list[ContentBlock] = []
    remaining = text
    while remaining:
        if len(remaining) <= max_chars:
            parts.append(ContentBlock(text=remaining, page_number=block.page_number))
            break
        window = remaining[:max_chars]
        # Prefer last whitespace in window.
        split_at = window.rfind(" ")
        if split_at < max_chars // 4:
            split_at = max_chars
        piece = remaining[:split_at].rstrip()
        remaining = remaining[split_at:].lstrip()
        if piece:
            parts.append(ContentBlock(text=piece, page_number=block.page_number))
        if not remaining:
            break
    return parts
