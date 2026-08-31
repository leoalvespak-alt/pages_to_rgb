"""Structural chunking — §24.2.

Preserves titles, chapters, sections, pages, tables, and topic boundaries.
Fixed-size naive splitting is not the only rule: hierarchy-first, then budget-fill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum


class SectionLevel(StrEnum):
    H1 = "h1"
    H2 = "h2"
    H3 = "h3"
    PARAGRAPH = "paragraph"
    TABLE = "table"
    LIST = "list"


@dataclass
class TextBlock:
    level: SectionLevel
    text: str
    page_number: int | None = None
    section_path: list[str] = field(default_factory=list)


@dataclass
class Chunk:
    text: str
    chunk_index: int
    page_number: int | None = None
    section: str | None = None
    token_count: int = 0
    extra: dict[str, object] = field(default_factory=dict)

    @property
    def metadata(self) -> dict[str, object]:
        return {
            "chunk_index": self.chunk_index,
            "page_number": self.page_number,
            "section": self.section,
            "token_count": self.token_count,
            **self.extra,
        }


_HEADING_RE = re.compile(
    r"^(#{1,6})\s+(.+)$",
    re.MULTILINE,
)
_TABLE_RE = re.compile(r"(\|.+\|[\r\n]+)+", re.MULTILINE)
_PAGE_BREAK_RE = re.compile(r"(?:^|\n)---page-(\d+)---(?:\n|$)")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")


def _approx_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _extract_blocks(text: str) -> list[TextBlock]:
    """Parse markdown/plain text into structural blocks."""
    blocks: list[TextBlock] = []
    current_page: int | None = None
    section_stack: list[str] = []
    pos = 0

    text = text.strip()
    lines = text.splitlines(keepends=True)
    i = 0
    buffer_lines: list[str] = []

    def _flush_buffer() -> None:
        joined = "".join(buffer_lines).strip()
        if joined:
            blocks.append(
                TextBlock(
                    level=SectionLevel.PARAGRAPH,
                    text=joined,
                    page_number=current_page,
                    section_path=list(section_stack),
                )
            )
        buffer_lines.clear()

    while i < len(lines):
        line = lines[i]

        # Page break marker
        m = _PAGE_BREAK_RE.match(line)
        if m:
            _flush_buffer()
            current_page = int(m.group(1))
            i += 1
            continue

        # Heading detection
        hm = re.match(r"^(#{1,6})\s+(.+)$", line.rstrip())
        if hm:
            _flush_buffer()
            depth = len(hm.group(1))
            title = hm.group(2).strip()
            level = [
                SectionLevel.H1,
                SectionLevel.H2,
                SectionLevel.H3,
                SectionLevel.H3,
                SectionLevel.H3,
                SectionLevel.H3,
            ][depth - 1]
            # Maintain stack
            while len(section_stack) >= depth:
                section_stack.pop()
            section_stack.append(title)
            blocks.append(
                TextBlock(
                    level=level,
                    text=line.rstrip(),
                    page_number=current_page,
                    section_path=list(section_stack),
                )
            )
            i += 1
            continue

        # Table detection: collect all consecutive table lines
        if line.startswith("|"):
            _flush_buffer()
            table_lines = []
            while i < len(lines) and (lines[i].startswith("|") or lines[i].strip() == ""):
                table_lines.append(lines[i])
                i += 1
            blocks.append(
                TextBlock(
                    level=SectionLevel.TABLE,
                    text="".join(table_lines).strip(),
                    page_number=current_page,
                    section_path=list(section_stack),
                )
            )
            continue

        # List item
        if re.match(r"^\s*[-*+]\s", line) or re.match(r"^\s*\d+\.\s", line):
            # Collect consecutive list lines
            _flush_buffer()
            list_lines = []
            while i < len(lines) and (
                re.match(r"^\s*[-*+]\s", lines[i])
                or re.match(r"^\s*\d+\.\s", lines[i])
                or (list_lines and lines[i].startswith("  "))
            ):
                list_lines.append(lines[i])
                i += 1
            blocks.append(
                TextBlock(
                    level=SectionLevel.LIST,
                    text="".join(list_lines).strip(),
                    page_number=current_page,
                    section_path=list(section_stack),
                )
            )
            continue

        buffer_lines.append(line)
        i += 1

    _flush_buffer()

    # Fallback: if no blocks extracted, treat whole text as one paragraph
    if not blocks and text:
        blocks.append(TextBlock(level=SectionLevel.PARAGRAPH, text=text))

    del pos  # not used after refactor
    return blocks


def _section_label(block: TextBlock) -> str | None:
    if block.section_path:
        return " > ".join(block.section_path[-2:])
    return None


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    source_type: str = "plain",
) -> list[Chunk]:
    """Split text into structural chunks.

    Strategy (§24.2):
    1. Parse into structural blocks (headings, paragraphs, tables, lists).
    2. Fill chunks up to `chunk_size` tokens, preserving block boundaries.
    3. When a single block exceeds budget, split at sentence boundaries with overlap.
    """
    blocks = _extract_blocks(text)
    chunks: list[Chunk] = []
    idx = 0

    current_parts: list[str] = []
    current_tokens = 0
    current_page: int | None = None
    current_section: str | None = None

    def _emit(parts: list[str], page: int | None, section: str | None) -> None:
        nonlocal idx
        body = "\n\n".join(p for p in parts if p.strip())
        if not body.strip():
            return
        chunks.append(
            Chunk(
                text=body,
                chunk_index=idx,
                page_number=page,
                section=section,
                token_count=_approx_tokens(body),
            )
        )
        idx += 1

    for block in blocks:
        btokens = _approx_tokens(block.text)
        section = _section_label(block) or current_section
        page = block.page_number or current_page

        # Tables and headings always get their own chunk (preserve intact)
        if block.level in (SectionLevel.H1, SectionLevel.H2, SectionLevel.TABLE):
            if current_parts:
                _emit(current_parts, current_page, current_section)
                current_parts = []
                current_tokens = 0

            if btokens <= chunk_size:
                _emit([block.text], page, section)
            else:
                # Large table: emit as single chunk anyway (tables must stay intact)
                _emit([block.text], page, section)

            current_page = page
            current_section = section
            continue

        # Block fits in the current accumulator
        if current_tokens + btokens <= chunk_size:
            current_parts.append(block.text)
            current_tokens += btokens
            if page is not None:
                current_page = page
            current_section = section or current_section
            continue

        # Would overflow: emit current, then handle this block
        if current_parts:
            _emit(current_parts, current_page, current_section)
            # Overlap: keep last `overlap` tokens' worth of text
            overlap_text = " ".join(current_parts[-1].split()[-overlap:]) if overlap else ""
            current_parts = [overlap_text] if overlap_text.strip() else []
            current_tokens = _approx_tokens(overlap_text) if overlap_text.strip() else 0

        if btokens <= chunk_size:
            current_parts.append(block.text)
            current_tokens += btokens
            current_page = page
            current_section = section
        else:
            # Block too large: split at sentence boundaries
            sentences = _SENTENCE_END_RE.split(block.text)
            sentence_buffer: list[str] = []
            sentence_tokens = 0

            for sent in sentences:
                st = _approx_tokens(sent)
                if st > chunk_size:
                    # Sentence still too large — split by words
                    if sentence_buffer:
                        _emit(sentence_buffer, page, section)
                        sentence_buffer = []
                        sentence_tokens = 0
                    words = sent.split()
                    word_acc: list[str] = []
                    word_tokens = 0
                    for word in words:
                        wt = _approx_tokens(word)
                        if word_tokens + wt > chunk_size and word_acc:
                            _emit([" ".join(word_acc)], page, section)
                            tail_words = word_acc[-overlap:] if overlap else []
                            word_acc = tail_words[:]
                            word_tokens = sum(_approx_tokens(w) for w in word_acc)
                        word_acc.append(word)
                        word_tokens += wt
                    if word_acc:
                        sentence_buffer.append(" ".join(word_acc))
                        sentence_tokens = word_tokens
                    continue
                if sentence_tokens + st > chunk_size and sentence_buffer:
                    _emit(sentence_buffer, page, section)
                    tail = sentence_buffer[-1] if sentence_buffer else ""
                    sentence_buffer = [tail[-overlap * 4 :]] if overlap else []
                    sentence_tokens = _approx_tokens(sentence_buffer[0]) if sentence_buffer else 0
                sentence_buffer.append(sent)
                sentence_tokens += st

            if sentence_buffer:
                current_parts.extend(sentence_buffer)
                current_tokens = sentence_tokens
                current_page = page
                current_section = section

    if current_parts:
        _emit(current_parts, current_page, current_section)

    return chunks


def chunk_document(
    text: str,
    *,
    chunk_size: int = 500,
    overlap: int = 50,
    discipline: str | None = None,
    subject: str | None = None,
    source_type: str = "plain",
) -> list[Chunk]:
    """Public API: chunk a document and attach discipline/subject metadata."""
    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap, source_type=source_type)
    for c in chunks:
        if discipline is not None:
            c.extra["discipline"] = discipline
        if subject is not None:
            c.extra["subject"] = subject
    return chunks
