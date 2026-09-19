"""Intermediate structures for policy parsing and chunking."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ContentBlock:
    """A paragraph, list, or table-like text block within a section."""

    text: str
    page_number: int | None = None


@dataclass
class ParsedSection:
    """A heading-scoped section of a policy source."""

    section_id: str | None
    section_title: str | None
    level: int
    blocks: list[ContentBlock] = field(default_factory=list)
    page_number: int | None = None

    @property
    def joined_text(self) -> str:
        return "\n\n".join(b.text for b in self.blocks if b.text.strip())


@dataclass
class ParsedSource:
    """Normalized extraction result before chunking."""

    sections: list[ParsedSection]
    source_filename: str | None = None
    full_text: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreparedChunk:
    """Deterministic chunk ready for PolicyChunk persistence."""

    chunk_index: int
    section_id: str | None
    section_title: str | None
    content: str
    content_hash: str
    source_filename: str | None
    page_number: int | None
