"""Document ingestion pipeline — §24.

10 stages: upload -> extract -> normalize -> split -> metadata
            -> embed -> pgvector -> FTS -> validate -> active.

Each stage is a pure function or async function. The document only becomes
active=true at the end (stage 10). If any stage fails, the document stays inactive.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.rag.chunking import Chunk, chunk_document

if TYPE_CHECKING:
    from src.pages_to_audio.domain.ports.embedding import EmbeddingProvider

logger = get_logger(__name__)


class SourceType(StrEnum):
    PDF = "pdf"
    MARKDOWN = "markdown"
    TXT = "txt"
    CSV = "csv"
    PASTE = "paste"


SUPPORTED_TYPES = {
    SourceType.PDF,
    SourceType.MARKDOWN,
    SourceType.TXT,
    SourceType.CSV,
    SourceType.PASTE,
}


@dataclass
class IngestRequest:
    title: str
    source_type: SourceType
    content: bytes
    discipline: str | None = None
    subject: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class IngestResult:
    sha256: str
    chunk_count: int
    storage_key: str
    document_id: str | None = None


@dataclass
class ChunkEmbedding:
    chunk: Chunk
    embedding: list[float]


# ---------------------------------------------------------------------------
# Stage 1: SHA-256 + deduplication key
# ---------------------------------------------------------------------------


def compute_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# Stage 2: Extract text from source
# ---------------------------------------------------------------------------


def extract_text(content: bytes, source_type: SourceType) -> str:
    """Extract plain text from the raw content bytes."""
    if source_type == SourceType.PDF:
        return _extract_pdf(content)
    if source_type in (SourceType.MARKDOWN, SourceType.TXT, SourceType.PASTE):
        try:
            return content.decode("utf-8", errors="replace")
        except Exception as exc:
            raise NonRetryableError(
                f"Text decode failed: {exc}",
                reason_code=ReasonCode.KNOWLEDGE_EXTRACTION_FAILED,
            ) from exc
    if source_type == SourceType.CSV:
        return _extract_csv(content)
    raise NonRetryableError(
        f"Unsupported source type: {source_type}",
        reason_code=ReasonCode.KNOWLEDGE_UNSUPPORTED_FORMAT,
    )


def _extract_pdf(content: bytes) -> str:
    try:
        import pypdf  # type: ignore[import-untyped]

        reader = pypdf.PdfReader(io.BytesIO(content))
        pages: list[str] = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            pages.append(f"---page-{i + 1}---\n{text}")
        return "\n\n".join(pages)
    except ImportError as exc:
        raise NonRetryableError(
            "pypdf not installed — cannot extract PDF",
            reason_code=ReasonCode.KNOWLEDGE_EXTRACTION_FAILED,
        ) from exc
    except Exception as exc:
        raise RetryableError(
            f"PDF extraction failed: {exc}",
            reason_code=ReasonCode.KNOWLEDGE_EXTRACTION_FAILED,
        ) from exc


def _extract_csv(content: bytes) -> str:
    import csv

    try:
        text = content.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return ""
        # Format as markdown table
        header = "| " + " | ".join(rows[0]) + " |"
        separator = "| " + " | ".join(["---"] * len(rows[0])) + " |"
        body = "\n".join("| " + " | ".join(r) + " |" for r in rows[1:])
        return f"{header}\n{separator}\n{body}"
    except Exception as exc:
        raise NonRetryableError(
            f"CSV extraction failed: {exc}",
            reason_code=ReasonCode.KNOWLEDGE_EXTRACTION_FAILED,
        ) from exc


# ---------------------------------------------------------------------------
# Stage 3: Normalize text
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """Normalize whitespace, remove control characters, standardize line endings."""
    import re

    # Remove carriage returns
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove null bytes and other control chars (except newline/tab)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    # Collapse 3+ blank lines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Stage 4: Split into chunks
# ---------------------------------------------------------------------------


def split_into_chunks(
    text: str,
    *,
    chunk_size: int,
    overlap: int,
    discipline: str | None,
    subject: str | None,
    source_type: str,
) -> list[Chunk]:
    return chunk_document(
        text,
        chunk_size=chunk_size,
        overlap=overlap,
        discipline=discipline,
        subject=subject,
        source_type=source_type,
    )


# ---------------------------------------------------------------------------
# Stage 5: Attach metadata to chunks
# ---------------------------------------------------------------------------


def attach_metadata(
    chunks: list[Chunk],
    *,
    discipline: str | None,
    subject: str | None,
    source_type: str,
    extra: dict[str, Any] | None = None,
) -> list[Chunk]:
    for c in chunks:
        c.extra.update(
            {
                "discipline": discipline,
                "subject": subject,
                "source_type": source_type,
                **(extra or {}),
            }
        )
    return chunks


# ---------------------------------------------------------------------------
# Stages 6-9: Embed + store (caller provides DB session + embedding provider)
# ---------------------------------------------------------------------------


async def embed_chunks(
    chunks: list[Chunk],
    provider: EmbeddingProvider,
) -> list[ChunkEmbedding]:
    """Stage 6: generate embeddings for all chunks."""
    texts = [c.text for c in chunks]
    try:
        vectors = await provider.embed_documents(texts)
    except Exception as exc:
        raise RetryableError(
            f"Embedding failed: {exc}",
            reason_code=ReasonCode.KNOWLEDGE_EMBEDDING_FAILED,
        ) from exc

    if len(vectors) != len(chunks):
        raise NonRetryableError(
            f"Embedding returned {len(vectors)} vectors for {len(chunks)} chunks",
            reason_code=ReasonCode.KNOWLEDGE_EMBEDDING_FAILED,
        )

    return [ChunkEmbedding(chunk=c, embedding=v) for c, v in zip(chunks, vectors, strict=True)]


# ---------------------------------------------------------------------------
# Stage 10: Mark document as active
# ---------------------------------------------------------------------------


async def validate_and_activate(
    document_id: str,
    chunk_count: int,
) -> bool:
    """Final validation gate. Returns True if document should be activated."""
    if chunk_count == 0:
        logger.warning(
            "knowledge_ingest_no_chunks",
            document_id=document_id,
        )
        return False
    logger.info(
        "knowledge_ingest_validated",
        document_id=document_id,
        chunk_count=chunk_count,
    )
    return True


# ---------------------------------------------------------------------------
# Full pipeline (no DB I/O — callers handle persistence)
# ---------------------------------------------------------------------------


async def run_extraction_pipeline(
    request: IngestRequest,
    *,
    embedding_provider: EmbeddingProvider,
    chunk_size: int = 500,
    overlap: int = 50,
) -> tuple[str, list[ChunkEmbedding]]:
    """Stages 1-6: compute sha256, extract, normalize, split, metadata, embed.

    Returns (sha256, list[ChunkEmbedding]).
    Does not touch the database — caller persists.
    """
    # Stage 1: hash
    sha256 = compute_sha256(request.content)
    logger.info(
        "knowledge_ingest_start",
        sha256=sha256,
        source_type=request.source_type,
        title=request.title,
    )

    # Stage 2: extract
    if request.source_type not in SUPPORTED_TYPES:
        raise NonRetryableError(
            f"Unsupported source type: {request.source_type}",
            reason_code=ReasonCode.KNOWLEDGE_UNSUPPORTED_FORMAT,
        )
    raw_text = extract_text(request.content, request.source_type)

    # Stage 3: normalize
    text = normalize_text(raw_text)
    if not text:
        raise NonRetryableError(
            "Document produced empty text after extraction",
            reason_code=ReasonCode.KNOWLEDGE_EXTRACTION_FAILED,
        )

    # Stage 4: split
    chunks = split_into_chunks(
        text,
        chunk_size=chunk_size,
        overlap=overlap,
        discipline=request.discipline,
        subject=request.subject,
        source_type=request.source_type,
    )

    # Stage 5: metadata
    attach_metadata(
        chunks,
        discipline=request.discipline,
        subject=request.subject,
        source_type=request.source_type,
        extra=request.metadata,
    )

    logger.info("knowledge_ingest_chunked", sha256=sha256, chunk_count=len(chunks))

    # Stage 6: embed
    embedded = await embed_chunks(chunks, embedding_provider)

    logger.info("knowledge_ingest_embedded", sha256=sha256, chunk_count=len(embedded))

    return sha256, embedded
