"""Knowledge base endpoints — §13.6 (S06: persistência real + auth + jobs rastreáveis).

POST   /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents
GET    /api/v1/knowledge/documents/{id}
DELETE /api/v1/knowledge/documents/{id}
POST   /api/v1/knowledge/documents/{id}/reindex
POST   /api/v1/knowledge/search-test
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy import text as sa_text

from apps.api.dependencies import UowDep
from src.pages_to_audio.auth.admin import require_admin_csrf, require_admin_session
from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.knowledge_chunk import KnowledgeChunk
from src.pages_to_audio.db.models.knowledge_document import KnowledgeDocument
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
from src.pages_to_audio.rag.retrieval import HybridRetriever

logger = get_logger(__name__)

# S06.1/A08: leitura e escrita exigem sessão admin (fronteira única; sem depender
# de ocultação no painel). Mutações exigem CSRF.
router = APIRouter(
    prefix="/knowledge",
    tags=["knowledge"],
    dependencies=[Depends(require_admin_session)],
)

MAX_DOC_BYTES = 20 * 1024 * 1024


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
    query: str = Field(min_length=1, max_length=2000)
    discipline: str | None = None
    subject: str | None = None
    top_k: int = Field(default=10, ge=1, le=50)


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


class ReindexResponse(BaseModel):
    status: str
    doc_id: str
    chunks_reindexed: int
    chunks_failed: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


async def _read_limited(file: UploadFile, *, limit: int = MAX_DOC_BYTES) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        part = await file.read(1024 * 1024)
        if not part:
            break
        total += len(part)
        if total > limit:
            raise HTTPException(status_code=413, detail="Document exceeds size limit")
        chunks.append(part)
    return b"".join(chunks)


EMBEDDING_UPDATE_SQL = (
    "UPDATE knowledge_chunks SET embedding = CAST(:emb AS vector(1536)) WHERE id = :cid"
)


def _embedding_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{v:.8f}" for v in vector) + "]"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/documents", status_code=201, response_model=DocumentResponse)
async def create_document(
    uow: UowDep,
    _csrf: Any = Depends(require_admin_csrf),
    file: UploadFile = File(...),
    title: str = Form(...),
    discipline: str | None = Form(None),
    subject: str | None = Form(None),
) -> DocumentResponse:
    """Upload and ingest a knowledge document — §13.6 (S06: persistente)."""
    if not title or len(title) > 300:
        raise HTTPException(status_code=422, detail="Title must contain 1-300 characters")
    content = await _read_limited(file)
    if not content:
        raise HTTPException(status_code=422, detail="Empty document")
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

    # S06.5: extração/fragmentação (CPU-bound/síncrona) fora do event loop.
    def _extract() -> tuple[str, list[Any]]:
        import asyncio as _asyncio

        return _asyncio.run(
            run_extraction_pipeline(
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
        )

    try:
        sha256, embedded = await asyncio.to_thread(_extract)
    except NonRetryableError as exc:
        raise HTTPException(
            status_code=422,
            detail={"reason_code": exc.reason_code, "message": str(exc)},
        ) from exc
    except RetryableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # Deduplicação por sha256 (persistente).
    existing = await uow.session.scalar(
        select(KnowledgeDocument).where(KnowledgeDocument.sha256 == sha256)
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "reason_code": ReasonCode.KNOWLEDGE_DOCUMENT_EXISTS,
                "existing_id": str(existing.id),
            },
        )

    doc_id = uuid.uuid4()
    storage_key = f"knowledge/{doc_id}/original"
    # Upload do original para o storage real (S06.2: sem chave sem upload).
    try:
        from src.pages_to_audio.storage import get_storage_adapter

        storage = get_storage_adapter()
        await storage.put_object(
            "knowledge",
            storage_key,
            content,
            file.content_type or "application/octet-stream",
            sha256=sha256,
            overwrite=True,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=503, detail=f"Knowledge storage unavailable: {exc}"
        ) from exc

    doc = KnowledgeDocument(
        id=doc_id,
        title=title,
        discipline=discipline,
        subject=subject,
        source_type=source_type.value,
        storage_key=storage_key,
        sha256=sha256,
        active=False,
    )
    uow.session.add(doc)
    await uow.session.flush()

    for ce in embedded:
        chunk = KnowledgeChunk(
            document_id=doc_id,
            chunk_index=ce.chunk.chunk_index,
            text_=ce.chunk.text,
            page_number=ce.chunk.page_number,
            section=ce.chunk.section,
            metadata_=dict(ce.chunk.metadata or {}),
        )
        uow.session.add(chunk)
        await uow.session.flush()
        # embedding VECTOR(1536): escrita via SQL tipado (S06.3: cast explícito).
        await uow.session.execute(
            sa_text(EMBEDDING_UPDATE_SQL),
            {"emb": _embedding_literal(list(ce.embedding)), "cid": str(chunk.id)},
        )

    activated = await validate_and_activate(str(doc_id), len(embedded))
    doc.active = activated
    uow.session.add(
        AuditEvent(
            session_id=None,
            event_type="KNOWLEDGE_DOCUMENT_INDEXED",
            stage="SYSTEM",
            severity="INFO",
            actor_type="admin",
            payload={
                "document_id": str(doc_id),
                "sha256": sha256,
                "chunk_count": len(embedded),
                "active": activated,
            },
        )
    )
    await uow.session.flush()

    logger.info(
        "knowledge_document_created",
        doc_id=str(doc_id),
        sha256=sha256,
        chunk_count=len(embedded),
        activated=activated,
    )
    return DocumentResponse(
        id=str(doc_id),
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
    uow: UowDep,
    discipline: str | None = Query(None),
    subject: str | None = Query(None),
    active_only: bool = Query(True),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> list[DocumentResponse]:
    """List knowledge documents with optional filters — §13.6 (S06: persistente + paginado)."""
    stmt = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    if active_only:
        stmt = stmt.where(KnowledgeDocument.active.is_(True))
    if discipline:
        stmt = stmt.where(KnowledgeDocument.discipline == discipline)
    if subject:
        stmt = stmt.where(KnowledgeDocument.subject == subject)
    stmt = stmt.offset((page - 1) * limit).limit(limit)
    rows = (await uow.session.execute(stmt)).scalars().all()
    out: list[DocumentResponse] = []
    for doc in rows:
        count = (
            await uow.session.scalar(
                select(func.count())
                .select_from(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == doc.id)
            )
            or 0
        )
        out.append(
            DocumentResponse(
                id=str(doc.id),
                title=doc.title,
                discipline=doc.discipline,
                subject=doc.subject,
                source_type=doc.source_type,
                sha256=doc.sha256,
                active=bool(doc.active),
                chunk_count=int(count),
            )
        )
    return out


@router.get("/documents/{doc_id}", response_model=DocumentResponse)
async def get_document(doc_id: str, uow: UowDep) -> DocumentResponse:
    """Get a single knowledge document — §13.6."""
    try:
        did = uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid document id") from exc
    doc = await uow.session.get(KnowledgeDocument, did)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={"reason_code": ReasonCode.KNOWLEDGE_NOT_FOUND},
        )
    count = (
        await uow.session.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == doc.id)
        )
        or 0
    )
    return DocumentResponse(
        id=str(doc.id),
        title=doc.title,
        discipline=doc.discipline,
        subject=doc.subject,
        source_type=doc.source_type,
        sha256=doc.sha256,
        active=bool(doc.active),
        chunk_count=int(count),
    )


@router.delete("/documents/{doc_id}", status_code=204)
async def delete_document(
    doc_id: str,
    uow: UowDep,
    _csrf: Any = Depends(require_admin_csrf),
    physical: bool = Query(False, description="Physical delete (default: logical active=false)"),
) -> None:
    """Logical delete (active=false) or physical — §13.6."""
    try:
        did = uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid document id") from exc
    doc = await uow.session.get(KnowledgeDocument, did)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={"reason_code": ReasonCode.KNOWLEDGE_NOT_FOUND},
        )
    if physical:
        await uow.session.execute(
            sa_text("DELETE FROM knowledge_chunks WHERE document_id = :did"), {"did": str(did)}
        )
        await uow.session.delete(doc)
        logger.info("knowledge_document_deleted_physical", doc_id=doc_id)
    else:
        doc.active = False
        logger.info("knowledge_document_deactivated", doc_id=doc_id)
    uow.session.add(
        AuditEvent(
            session_id=None,
            event_type="KNOWLEDGE_DOCUMENT_DELETED",
            stage="SYSTEM",
            severity="INFO",
            actor_type="admin",
            payload={"document_id": doc_id, "physical": physical},
        )
    )
    await uow.session.flush()


@router.post("/documents/{doc_id}/reindex", response_model=ReindexResponse)
async def reindex_document(
    doc_id: str, uow: UowDep, _csrf: Any = Depends(require_admin_csrf)
) -> ReindexResponse:
    """Re-embed all chunks of a document — §13.6 (S06: reindexação real e verificável)."""
    try:
        did = uuid.UUID(doc_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid document id") from exc
    doc = await uow.session.get(KnowledgeDocument, did)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail={"reason_code": ReasonCode.KNOWLEDGE_NOT_FOUND},
        )
    chunks = (
        (
            await uow.session.execute(
                select(KnowledgeChunk)
                .where(KnowledgeChunk.document_id == did)
                .order_by(KnowledgeChunk.chunk_index)
            )
        )
        .scalars()
        .all()
    )
    if not chunks:
        raise HTTPException(status_code=409, detail="Document has no chunks to reindex")
    provider = _get_embedding_provider()
    texts = [c.text_ for c in chunks]
    try:
        vectors = await provider.embed_documents(texts)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Embedding unavailable: {exc}") from exc
    if len(vectors) != len(chunks):
        raise HTTPException(status_code=502, detail="Embedding returned mismatched vector count")
    failed = 0
    for chunk, vector in zip(chunks, vectors, strict=True):
        try:
            await uow.session.execute(
                sa_text(EMBEDDING_UPDATE_SQL),
                {"emb": _embedding_literal(list(vector)), "cid": str(chunk.id)},
            )
        except Exception:
            failed += 1
    reindexed = len(chunks) - failed
    uow.session.add(
        AuditEvent(
            session_id=None,
            event_type="KNOWLEDGE_DOCUMENT_REINDEXED",
            stage="SYSTEM",
            severity="INFO" if failed == 0 else "WARNING",
            actor_type="admin",
            payload={"document_id": doc_id, "reindexed": reindexed, "failed": failed},
        )
    )
    await uow.session.flush()
    logger.info("knowledge_reindexed", doc_id=doc_id, reindexed=reindexed, failed=failed)
    return ReindexResponse(
        status="completed", doc_id=doc_id, chunks_reindexed=reindexed, chunks_failed=failed
    )


@router.post("/search-test", response_model=SearchTestResponse)
async def search_test(req: SearchTestRequest, uow: UowDep) -> SearchTestResponse:
    """Test retrieval without calling LLM — §25.2 / §13.6 (S06: busca real persistente).

    Falha de infraestrutura retorna 503 explícito — nunca lista vazia mascarada (A24/A25).
    """
    import time

    settings = get_settings()
    provider = _get_embedding_provider()
    retriever = HybridRetriever(
        provider,
        top_k=req.top_k,
        rrf_k=settings.RAG_RRF_K,
        reranker_enabled=settings.RERANKER_ENABLED,
    )
    start = time.monotonic()
    try:
        result = await retriever.retrieve(
            "search-test",
            req.query,
            db_session=uow.session,
            discipline=req.discipline,
            subject=req.subject,
            top_k=req.top_k,
        )
    except RetryableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except NonRetryableError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
            for h in result.hits
        ],
        metadata={
            "latency_ms": round(elapsed_ms, 2),
            "reranker_enabled": settings.RERANKER_ENABLED,
            **result.metadata,
        },
    )
