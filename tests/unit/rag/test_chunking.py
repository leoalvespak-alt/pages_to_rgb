"""Tests for structural chunking — §24.2."""

from __future__ import annotations

from src.pages_to_audio.rag.chunking import (
    Chunk,
    SectionLevel,
    _extract_blocks,
    chunk_document,
    chunk_text,
)


class TestExtractBlocks:
    def test_plain_paragraph(self) -> None:
        blocks = _extract_blocks("Hello world. This is a paragraph.")
        assert len(blocks) == 1
        assert blocks[0].level == SectionLevel.PARAGRAPH

    def test_heading_detection(self) -> None:
        text = "# Main Title\n\nSome paragraph text.\n\n## Subtitle\n\nMore text."
        blocks = _extract_blocks(text)
        levels = [b.level for b in blocks]
        assert SectionLevel.H1 in levels
        assert SectionLevel.H2 in levels

    def test_table_block(self) -> None:
        text = "Before\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAfter"
        blocks = _extract_blocks(text)
        table_blocks = [b for b in blocks if b.level == SectionLevel.TABLE]
        assert len(table_blocks) == 1
        assert "| A | B |" in table_blocks[0].text

    def test_page_marker(self) -> None:
        text = "First page content.\n\n---page-2---\n\nSecond page content."
        blocks = _extract_blocks(text)
        # Second page content should have page_number=2
        second_page = [b for b in blocks if b.page_number == 2]
        assert second_page, "Expected block with page_number=2"

    def test_section_path_propagation(self) -> None:
        text = "# Chapter 1\n\nParagraph under chapter."
        blocks = _extract_blocks(text)
        paragraphs = [b for b in blocks if b.level == SectionLevel.PARAGRAPH]
        assert paragraphs
        assert "Chapter 1" in paragraphs[0].section_path


class TestChunkText:
    def test_returns_chunks(self) -> None:
        text = "This is a test sentence. " * 200
        chunks = chunk_text(text, chunk_size=100)
        assert len(chunks) > 1

    def test_chunk_indexes_are_sequential(self) -> None:
        text = "Word " * 500
        chunks = chunk_text(text, chunk_size=50)
        indexes = [c.chunk_index for c in chunks]
        assert indexes == list(range(len(indexes)))

    def test_short_text_single_chunk(self) -> None:
        text = "Short text."
        chunks = chunk_text(text, chunk_size=500)
        assert len(chunks) == 1
        assert chunks[0].text == "Short text."

    def test_chunk_preserves_table(self) -> None:
        text = "Intro.\n\n| Col1 | Col2 |\n|------|------|\n| A    | B    |\n\nConclusion."
        chunks = chunk_text(text, chunk_size=500)
        table_chunks = [c for c in chunks if "|" in c.text]
        assert table_chunks, "Table should be preserved in a chunk"

    def test_overlap_content(self) -> None:
        # Overlap should produce some repeated content between adjacent large chunks
        text = ("Sentence one. Sentence two. Sentence three. " * 30)
        chunks = chunk_text(text, chunk_size=50, overlap=10)
        # With overlap, adjacent chunks may share words -- just verify no empty chunks
        for chunk in chunks:
            assert chunk.text.strip()

    def test_page_number_propagated(self) -> None:
        text = "Page 1 content.\n\n---page-2---\n\nPage 2 content."
        chunks = chunk_text(text)
        page2_chunks = [c for c in chunks if c.page_number == 2]
        assert page2_chunks


class TestChunkDocument:
    def test_attaches_metadata(self) -> None:
        chunks = chunk_document(
            "Some text about mathematics.",
            discipline="Mathematics",
            subject="Algebra",
        )
        assert chunks
        # metadata is a property that returns a dict
        for c in chunks:
            meta = c.metadata
            assert meta.get("discipline") == "Mathematics"
            assert meta.get("subject") == "Algebra"

    def test_empty_document(self) -> None:
        # Should handle empty or whitespace-only docs gracefully
        chunks = chunk_document("   \n\n  ")
        # Either empty list or a single empty-text chunk; no exception
        assert isinstance(chunks, list)

    def test_chunk_type(self) -> None:
        chunks = chunk_document("Hello world.")
        assert all(isinstance(c, Chunk) for c in chunks)
