"""Hybrid retrieval — §25.

7 stages:
  1. query expansion
  2. FTS (full-text search, Portuguese)
  3. vector search (pgvector cosine)
  4. Reciprocal Rank Fusion (RRF)
  5. filters by discipline/subject
  6. reranking (pluggable cross-encoder; disabled by default)
  7. top evidence selection

Output contract per §25.1:
  {question_id, query, hits[{chunk_id, document_id, score, text, page, source}]}
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.pages_to_audio.common.errors import ReasonCode, RetryableError
from src.pages_to_audio.observability.logging import get_logger

if TYPE_CHECKING:
    from src.pages_to_audio.domain.ports.embedding import EmbeddingProvider

logger = get_logger(__name__)


@dataclass(frozen=True)
class RetrievalHit:
    """A single retrieval result — §25.1 contract."""

    chunk_id: str
    document_id: str
    score: float
    text: str
    page: int | None
    source: str


@dataclass
class RetrievalResult:
    """Full retrieval result for a question — §25.1 contract."""

    question_id: str
    query: str
    hits: list[RetrievalHit] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Stage 1: Query expansion
# ---------------------------------------------------------------------------


def expand_query(query: str) -> list[str]:
    """Lightweight query expansion — §25 stage 1.

    Returns the original query plus short paraphrases.
    In V1 this is deterministic (no LLM call).
    """
    # Simple heuristic: strip trailing punctuation, add Portuguese educational keywords
    clean = query.strip().rstrip("?.!,;:")
    variants = [clean]
    # Avoid expanding if already long (> 15 words)
    if len(clean.split()) <= 15:
        variants.append(f"questão sobre {clean}")
    return variants[:2]


# ---------------------------------------------------------------------------
# Stage 4: Reciprocal Rank Fusion (RRF)
# ---------------------------------------------------------------------------


def reciprocal_rank_fusion(
    ranked_lists: list[list[str]],
    k: int = 60,
) -> list[tuple[str, float]]:
    """Fuse multiple ranked lists using RRF.

    Args:
        ranked_lists: Each inner list is a ranked list of IDs (best first).
        k: RRF constant (default 60 per §25).

    Returns:
        List of (id, fused_score) sorted descending.
    """
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (k + rank)

    return sorted(scores.items(), key=lambda x: x[1], reverse=True)


# ---------------------------------------------------------------------------
# Retriever — wraps all 7 stages
# ---------------------------------------------------------------------------


class HybridRetriever:
    """Executes the 7-stage hybrid retrieval pipeline against Postgres.

    FTS and vector search both run against the `knowledge_chunks` table.
    The caller must pass an async SQLAlchemy session.
    """

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        top_k: int = 10,
        rrf_k: int = 60,
        reranker_enabled: bool = False,
    ) -> None:
        self._embed = embedding_provider
        self._top_k = top_k
        self._rrf_k = rrf_k
        self._reranker_enabled = reranker_enabled

    async def retrieve(
        self,
        question_id: str,
        query: str,
        *,
        db_session: Any,
        discipline: str | None = None,
        subject: str | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        """Run full 7-stage pipeline. Returns RetrievalResult."""
        effective_top_k = top_k or self._top_k

        # Stage 1: query expansion
        queries = expand_query(query)
        primary_query = queries[0]

        # Stage 3: embed the primary query for vector search
        try:
            query_embedding = await self._embed.embed_query(primary_query)
        except Exception as exc:
            raise RetryableError(
                f"Embedding query failed: {exc}",
                reason_code=ReasonCode.RETRIEVAL_FAILED,
            ) from exc

        # Stage 2: FTS
        fts_rows = await self._run_fts(db_session, queries, discipline, subject)

        # Stage 3: vector search
        vector_rows = await self._run_vector(
            db_session, query_embedding, discipline, subject, effective_top_k * 2
        )

        # Stage 4: RRF
        fts_ids = [str(r["chunk_id"]) for r in fts_rows]
        vec_ids = [str(r["chunk_id"]) for r in vector_rows]
        fused = reciprocal_rank_fusion([fts_ids, vec_ids], k=self._rrf_k)

        # Stage 5: filters (already applied in SQL queries above; here refine if needed)
        all_rows_by_id: dict[str, dict[str, Any]] = {}
        for r in fts_rows + vector_rows:
            all_rows_by_id[str(r["chunk_id"])] = r

        # Stage 6: reranker (pluggable, disabled by default per settings)
        if self._reranker_enabled:
            fused = await self._rerank(fused, primary_query, all_rows_by_id)

        # Stage 7: top evidence
        hits: list[RetrievalHit] = []
        for chunk_id, score in fused[:effective_top_k]:
            row = all_rows_by_id.get(chunk_id)
            if row is None:
                continue
            hits.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    document_id=str(row.get("document_id", "")),
                    score=score,
                    text=str(row.get("text", "")),
                    page=row.get("page_number"),
                    source=str(row.get("title", "")),
                )
            )

        logger.info(
            "retrieval_complete",
            question_id=question_id,
            query=primary_query,
            fts_hits=len(fts_rows),
            vector_hits=len(vector_rows),
            fused_hits=len(hits),
        )

        return RetrievalResult(
            question_id=question_id,
            query=primary_query,
            hits=hits,
            metadata={
                "queries": queries,
                "fts_count": len(fts_rows),
                "vector_count": len(vector_rows),
                "rrf_k": self._rrf_k,
                "reranker": self._reranker_enabled,
            },
        )

    async def _run_fts(
        self,
        db: Any,
        queries: list[str],
        discipline: str | None,
        subject: str | None,
    ) -> list[dict[str, Any]]:
        """Stage 2: Full-text search using Portuguese tsvector."""
        from sqlalchemy import text as sa_text

        # Build Portuguese tsquery from all query variants
        tsquery_parts = []
        for q in queries:
            words = [w for w in q.split() if len(w) > 2]
            if words:
                tsquery_parts.append(" & ".join(words))

        if not tsquery_parts:
            return []

        combined_tsquery = " | ".join(f"({p})" for p in tsquery_parts)

        sql = """
            SELECT
                kc.id AS chunk_id,
                kc.document_id,
                kc.text,
                kc.page_number,
                kd.title,
                ts_rank(kc.fts, to_tsquery('portuguese_unaccent', :tsquery)) AS fts_score
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kd.id = kc.document_id
            WHERE kd.active = true
              AND kc.fts @@ to_tsquery('portuguese_unaccent', :tsquery)
              AND (:discipline IS NULL OR kd.discipline = :discipline)
              AND (:subject IS NULL OR kd.subject = :subject)
            ORDER BY fts_score DESC
            LIMIT 20
        """

        try:
            result = await db.execute(
                sa_text(sql),
                {
                    "tsquery": combined_tsquery,
                    "discipline": discipline,
                    "subject": subject,
                },
            )
            return [dict(row._mapping) for row in result]
        except Exception as exc:
            logger.warning("fts_search_failed", error=str(exc))
            return []

    async def _run_vector(
        self,
        db: Any,
        embedding: list[float],
        discipline: str | None,
        subject: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Stage 3: pgvector cosine similarity search."""
        from sqlalchemy import text as sa_text

        embedding_str = "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"

        sql = """
            SELECT
                kc.id AS chunk_id,
                kc.document_id,
                kc.text,
                kc.page_number,
                kd.title,
                1 - (kc.embedding <=> :embedding::vector) AS vector_score
            FROM knowledge_chunks kc
            JOIN knowledge_documents kd ON kd.id = kc.document_id
            WHERE kd.active = true
              AND kc.embedding IS NOT NULL
              AND (:discipline IS NULL OR kd.discipline = :discipline)
              AND (:subject IS NULL OR kd.subject = :subject)
            ORDER BY kc.embedding <=> :embedding::vector
            LIMIT :limit
        """

        try:
            result = await db.execute(
                sa_text(sql),
                {
                    "embedding": embedding_str,
                    "discipline": discipline,
                    "subject": subject,
                    "limit": limit,
                },
            )
            return [dict(row._mapping) for row in result]
        except Exception as exc:
            logger.warning("vector_search_failed", error=str(exc))
            return []

    async def _rerank(
        self,
        fused: list[tuple[str, float]],
        query: str,
        rows_by_id: dict[str, dict[str, Any]],
    ) -> list[tuple[str, float]]:
        """Stage 6: Rerank with cross-encoder (stub — disabled by default)."""
        # Pluggable: in a full implementation this calls a cross-encoder model.
        # For now, return fused unchanged when called.
        return fused


# ---------------------------------------------------------------------------
# Public factory
# ---------------------------------------------------------------------------


def build_retriever(
    embedding_provider: EmbeddingProvider,
    *,
    top_k: int = 10,
    rrf_k: int = 60,
    reranker_enabled: bool = False,
) -> HybridRetriever:
    return HybridRetriever(
        embedding_provider=embedding_provider,
        top_k=top_k,
        rrf_k=rrf_k,
        reranker_enabled=reranker_enabled,
    )
