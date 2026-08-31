"""Tests for the document ingest pipeline — §24."""

from __future__ import annotations

import pytest

from src.pages_to_audio.common.errors import NonRetryableError
from src.pages_to_audio.llm.providers.fake_embedding import FakeEmbeddingProvider
from src.pages_to_audio.rag.ingest import (
    IngestRequest,
    SourceType,
    attach_metadata,
    compute_sha256,
    embed_chunks,
    extract_text,
    normalize_text,
    run_extraction_pipeline,
    split_into_chunks,
    validate_and_activate,
)


class TestComputeSha256:
    def test_deterministic(self) -> None:
        h1 = compute_sha256(b"hello")
        h2 = compute_sha256(b"hello")
        assert h1 == h2

    def test_length_64(self) -> None:
        h = compute_sha256(b"test data")
        assert len(h) == 64

    def test_different_content_different_hash(self) -> None:
        assert compute_sha256(b"aaa") != compute_sha256(b"bbb")


class TestExtractText:
    def test_txt(self) -> None:
        text = extract_text(b"Hello world", SourceType.TXT)
        assert text == "Hello world"

    def test_markdown(self) -> None:
        md = b"# Title\n\nParagraph text."
        text = extract_text(md, SourceType.MARKDOWN)
        assert "Title" in text

    def test_paste(self) -> None:
        text = extract_text(b"pasted text", SourceType.PASTE)
        assert text == "pasted text"

    def test_csv_becomes_table(self) -> None:
        csv_content = b"name,value\nalpha,1\nbeta,2"
        text = extract_text(csv_content, SourceType.CSV)
        assert "|" in text  # should be markdown table

    def test_unsupported_format_raises(self) -> None:
        with pytest.raises(NonRetryableError):
            extract_text(b"content", "docx")  # type: ignore[arg-type]


class TestNormalizeText:
    def test_removes_null_bytes(self) -> None:
        text = normalize_text("hello\x00world")
        assert "\x00" not in text

    def test_collapses_blank_lines(self) -> None:
        text = normalize_text("line1\n\n\n\n\nline2")
        assert text.count("\n") <= 3

    def test_strips_whitespace(self) -> None:
        text = normalize_text("  hello world  ")
        assert text == "hello world"

    def test_preserves_newlines(self) -> None:
        text = normalize_text("line1\nline2")
        assert "line1" in text and "line2" in text


class TestSplitIntoChunks:
    def test_returns_chunks(self) -> None:
        text = "Word " * 300
        chunks = split_into_chunks(
            text, chunk_size=100, overlap=10, discipline=None, subject=None, source_type="txt"
        )
        assert len(chunks) > 1

    def test_no_empty_chunks(self) -> None:
        text = "Sentence one. Sentence two. " * 50
        chunks = split_into_chunks(
            text, chunk_size=50, overlap=5, discipline=None, subject=None, source_type="txt"
        )
        for c in chunks:
            assert c.text.strip()


class TestAttachMetadata:
    def test_attaches_discipline(self) -> None:
        text = "Some content."
        chunks = split_into_chunks(
            text, chunk_size=500, overlap=0, discipline=None, subject=None, source_type="txt"
        )
        attach_metadata(
            chunks, discipline="Física", subject="Mecânica", source_type="txt"
        )
        for c in chunks:
            assert c.metadata.get("discipline") == "Física"  # type: ignore[attr-defined]
            assert c.metadata.get("subject") == "Mecânica"  # type: ignore[attr-defined]


class TestEmbedChunks:
    @pytest.mark.asyncio
    async def test_embeds_all_chunks(self) -> None:
        text = "Chunk content A. Chunk content B."
        chunks = split_into_chunks(
            text, chunk_size=20, overlap=0, discipline=None, subject=None, source_type="txt"
        )
        provider = FakeEmbeddingProvider(dimension=16)
        embedded = await embed_chunks(chunks, provider)
        assert len(embedded) == len(chunks)

    @pytest.mark.asyncio
    async def test_embedding_dimension(self) -> None:
        text = "Single chunk text."
        chunks = split_into_chunks(
            text, chunk_size=500, overlap=0, discipline=None, subject=None, source_type="txt"
        )
        provider = FakeEmbeddingProvider(dimension=64)
        embedded = await embed_chunks(chunks, provider)
        assert all(len(ce.embedding) == 64 for ce in embedded)


class TestValidateAndActivate:
    @pytest.mark.asyncio
    async def test_activates_with_chunks(self) -> None:
        result = await validate_and_activate("doc-123", chunk_count=5)
        assert result is True

    @pytest.mark.asyncio
    async def test_does_not_activate_empty(self) -> None:
        result = await validate_and_activate("doc-456", chunk_count=0)
        assert result is False


class TestRunExtractionPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_txt(self) -> None:
        request = IngestRequest(
            title="Test Document",
            source_type=SourceType.TXT,
            content=b"This is a knowledge document about mathematics. " * 20,
            discipline="Mathematics",
            subject="General",
        )
        provider = FakeEmbeddingProvider(dimension=32)
        sha256, embedded = await run_extraction_pipeline(
            request, embedding_provider=provider, chunk_size=100, overlap=10
        )
        assert len(sha256) == 64
        assert len(embedded) > 0
        assert all(len(ce.embedding) == 32 for ce in embedded)

    @pytest.mark.asyncio
    async def test_sha256_is_stable(self) -> None:
        request = IngestRequest(
            title="Stable",
            source_type=SourceType.TXT,
            content=b"Fixed content",
        )
        provider = FakeEmbeddingProvider(dimension=16)
        sha1, _ = await run_extraction_pipeline(
            request, embedding_provider=provider
        )
        sha2, _ = await run_extraction_pipeline(
            request, embedding_provider=provider
        )
        assert sha1 == sha2

    @pytest.mark.asyncio
    async def test_empty_content_raises(self) -> None:
        request = IngestRequest(
            title="Empty",
            source_type=SourceType.TXT,
            content=b"   ",
        )
        provider = FakeEmbeddingProvider(dimension=16)
        with pytest.raises(NonRetryableError):
            await run_extraction_pipeline(request, embedding_provider=provider)
