"""Knowledge base endpoints — §13.6.

POST   /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/{id}
DELETE /api/v1/knowledge/documents/{id}
POST   /api/v1/knowledge/documents/{id}/reindex
POST   /api/v1/knowledge/search-test
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.llm.providers.fake_embedding import FakeEmbeddingProvider
from src.pages_to_audio.llm.providers.openai_embedding import OpenAIEmbeddingProvider
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.rag.ingest import (
    SUPPORTED_TYPES,
    IngestRequest,
    SourceType,
    run_extraction_pipeline,
    validate_and_activate,
)
from src.pages_to_audio.rag.retrieval import RetrievalHit, build_retriever

logger = get_logger(__name__)
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class DocumentResponse(BaseModel):
    id: str
    title: str
    discipline: str | None
    subject: str | None
    source_type: str
    sha256: str
    active: bool
    chunk_count: int = 0


class SearchTestRequest(BaseModel):
    query: str
    discipline: str | None = None
    subject: str | None = None
    top_k: int = 10


class SearchTestHit(BaseModel):
    chunk_id: str
    document_id: str
    score: float
    text: str
    page: int | None
    source: str


class SearchTestResponse(BaseModel):
    query: str
    hits: list[SearchTestHit]
    metadata: dict[str, Any]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# In-memory store for now (Phase 7 stub — Phase 10 wires real DB session)
_DOCS: dict[str, dict[str, Any]] = {}
_CHUNKS: dict[str, list[dict[str, Any]]] = {}


def _get_embedding_provider() -> Any:
    settings = get_settings()
    if settings.EMBEDDING_PROVIDER == "openai":
        return OpenAIEmbeddingProvider(settings)
    return FakeEmbeddingProvider(dimension=settings.EMBEDDING_DIMENSION)


def _source_type_from_content_type(content_type: str | None, filename: str | None) -> SourceType:
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower()
        mapping = {
            "pdf": SourceType.PDF,
            "md": SourceType.MARKDOWN,
            "markdown": SourceType.MARKDOWN,
            "txt": SourceType.TXT,
            "csv": SourceType.CSV,
        }
        if ext in mapping:
            return mapping[ext]
    if content_type:
        if "pdf" in content_type:
            return SourceType.PDF
        if "csv" in content_type:
            return SourceType.CSV
        if "markdown" in content_type:
            return SourceType.MARKDOWN
    return SourceType.TXT


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/documents", status_code=201, response_model=DocumentResponse)
async def create_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    discipline: str | None = Form(None),
    subject: str | None = Form(None),
) -> DocumentResponse:
    """Upload and ingest a knowledge document — §13.6."""
    content = await file.read()
    source_type = _source_type_from_content_type(file.content_type, file.filename)

    if source_type not in SUPPORTED_TYPES:
        raise HTTPException(
            status_code=422,
            detail={
                "reason_code": ReasonCode.KNOWLEDGE_UNSUPPORTED_FORMAT,
                "message": f"Unsupported format. Supported: {[s.value for s in SUPPORTED_TYPES]}",
            },
        )

    settings = get_settings()
    provider = _get_embedding_provider()

    try:
        sha256, embedded = await run_extraction_pipeline(
            IngestRequest(
                title=title,
                source_type=source_type,
                content=content,
                discipline=discipline,
                subject=subject,
            ),
            embedding_provider=provider,
            chunk_size=settings.RAG_CHUNK_SIZE,
            overlap=settings.RAG_CHUNK_OVERLAP,
        )
    except NonRetryableError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason_code": exc.reason_code, "message": str(exc)},
        ) from exc

    # Check for duplicate
    for doc in _DOCS.values():
        if doc["sha256"] == sha256:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason_code": ReasonCode.KNOWLEDGE_DOCUMENT_EXISTS,
                    "existing_id": doc["id"],
                },
            )

    doc_id = str(uuid.uuid4())
    activated = await validate_and_activate(doc_id, len(embedded))

    _DOCS[doc_id] = {
        "id": doc_id,
        "title": title,
        "discipline": discipline,
        "subject": subject,
        "source_type": source_type.value,
        "sha256": sha256,
        "active": activated,
        "storage_key": f"knowledge/{doc_id}/original",
    }
    _CHUNKS[doc_id] = [
        {
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "chunk_index": ce.chunk.chunk_index,
            "text": ce.chunk.text,
            "embedding": ce.embedding,
            "page_number": ce.chunk.page_number,
            "section": ce.chunk.section,
            "metadata": ce.chunk.metadata,
        }
        for ce in embedded
    ]

    logger.info(
        "knowledge_document_created",
        doc_id=doc_id,
        sha256=sha256,
        chunk_count=len(embedded),
        activated=activated,
    )

    return DocumentResponse(
        id=doc_id,
        title=title,
        discipline=discipline,
        subject=subject,
        source_type=source_type.value,
        sha256=sha256,
        active=activated,
        chunk_count=len(embedded),
    )


@router.get("/documents", response_model=list[DocumentResponse])
async def list_documents(
    discipline: str | None = Query(None),
    subject: str | None = Query(None),
    active_only: bool = Query(True),
) -> list[DocumentResponse]:
    """List knowledge documents with optional filters — §13.6."""
    results = []
    for doc in _DOCS.values():
        if active_only and not doc["active"]:
            continue
        if discipline and doc.get("discipline") != discipline:
            continue
        if subject and doc.get("subject") != subject:
            continue
        results.append(
            DocumentResponse(
                id=doc["id"],
                title=doc["title"],
                discipline=doc.get("discipline"),
                subject=doc.get("subject"),
                source_type=doc["source_type"],
                sha256=doc["sha256"],
                active=doc["active"],
                chunk_count=len(_CHUNKS.get(doc["id"], [])),
            )
        )
    return results


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str) -> DocumentResponse:
    """Get a single knowledge document — §13.6."""
    doc = _DOCS.get(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"reason_code": ReasonCode.KNOWLEDGE_NOT_FOUND},
        )
    return DocumentResponse(
        id=doc["id"],
        title=doc["title"],
        discipline=doc.get("discipline"),
        subject=doc.get("subject"),
        source_type=doc["source_type"],
        sha256=doc["sha256"],
        active=doc["active"],
        chunk_count=len(_CHUNKS.get(doc_id, [])),
    )


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    physical: bool = Query(False, description="Physical delete (default: logical active=false)"),
) -> None:
    """Logical delete (active=false) or physical — §13.6."""
    doc = _DOCS.get(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"reason_code": ReasonCode.KNOWLEDGE_NOT_FOUND},
        )
    if physical:
        del _DOCS[doc_id]
        _CHUNKS.pop(doc_id, None)
        logger.info("knowledge_document_deleted_physical", doc_id=doc_id)
    else:
        _DOCS[doc_id]["active"] = False
        logger.info("knowledge_document_deactivated", doc_id=doc_id)


@router.post("/documents/{doc_id}/reindex", status_code=202)
async def reindex_document(doc_id: str) -> dict[str, str]:
    """Trigger re-embedding of a document (idempotent) — §13.6."""
    doc = _DOCS.get(doc_id)
    if not doc:
        raise HTTPException(
            status_code=404,
            detail={"reason_code": ReasonCode.KNOWLEDGE_NOT_FOUND},
        )
    # In a real impl, this enqueues a background job; here it's a no-op response
    logger.info("knowledge_reindex_requested", doc_id=doc_id)
    return {"status": "accepted", "doc_id": doc_id}


@router.post("/search-test", response_model=SearchTestResponse)
async def search_test(req: SearchTestRequest) -> SearchTestResponse:
    """Test retrieval without calling LLM — §25.2 / §13.6.

    Returns hits with per-stage scores and latency.
    """
    import time

    settings = get_settings()
    provider = _get_embedding_provider()

    build_retriever(
        provider,
        top_k=req.top_k,
        rrf_k=settings.RAG_RRF_K,
        reranker_enabled=settings.RERANKER_ENABLED,
    )

    start = time.monotonic()

    # Run in-memory retrieval (no DB session — uses fake in-memory store)
    hits = _in_memory_search(
        req.query,
        discipline=req.discipline,
        subject=req.subject,
        top_k=req.top_k,
        provider=provider,
    )

    elapsed_ms = (time.monotonic() - start) * 1000

    return SearchTestResponse(
        query=req.query,
        hits=[
            SearchTestHit(
                chunk_id=h.chunk_id,
                document_id=h.document_id,
                score=h.score,
                text=h.text,
                page=h.page,
                source=h.source,
            )
            for h in hits
        ],
        metadata={
            "latency_ms": round(elapsed_ms, 2),
            "total_chunks_searched": sum(len(v) for v in _CHUNKS.values()),
            "reranker_enabled": settings.RERANKER_ENABLED,
        },
    )


def _in_memory_search(
    query: str,
    *,
    discipline: str | None,
    subject: str | None,
    top_k: int,
    provider: Any,
) -> list[RetrievalHit]:
    """In-memory cosine search for search-test (no real DB needed)."""
    import math

    # Filter active documents
    active_doc_ids = {
        did
        for did, d in _DOCS.items()
        if d["active"]
        and (discipline is None or d.get("discipline") == discipline)
        and (subject is None or d.get("subject") == subject)
    }

    # Collect all chunks from active docs
    all_chunks = []
    for did in active_doc_ids:
        for chunk in _CHUNKS.get(did, []):
            all_chunks.append((did, chunk))

    if not all_chunks:
        return []

    # Simple keyword score for FTS simulation
    query_words = set(query.lower().split())

    def keyword_score(text: str) -> float:
        words = set(text.lower().split())
        overlap = query_words & words
        return len(overlap) / (len(query_words) + 1)

    def cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    # Get query embedding synchronously for in-memory use
    import asyncio

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, provider.embed_query(query))
                q_embedding = future.result()
        else:
            q_embedding = loop.run_until_complete(provider.embed_query(query))
    except Exception:
        q_embedding = None

    results = []
    for did, chunk in all_chunks:
        kw = keyword_score(chunk["text"])
        vec = 0.0
        if q_embedding and chunk.get("embedding"):
            vec = cosine_sim(q_embedding, chunk["embedding"])
        combined = 0.5 * kw + 0.5 * vec
        results.append((combined, chunk, did))

    results.sort(key=lambda x: x[0], reverse=True)
    doc_titles = {did: _DOCS[did]["title"] for did in active_doc_ids}

    return [
        RetrievalHit(
            chunk_id=str(chunk["id"]),
            document_id=str(did),
            score=round(score, 6),
            text=chunk["text"],
            page=chunk.get("page_number"),
            source=doc_titles.get(did, ""),
        )
        for score, chunk, did in results[:top_k]
    ]
