"""Tests for hybrid retrieval — §25, §7.7.3."""

from __future__ import annotations

import pytest

from src.pages_to_audio.llm.providers.fake_embedding import FakeEmbeddingProvider
from src.pages_to_audio.rag.retrieval import (
    HybridRetriever,
    RetrievalHit,
    RetrievalResult,
    build_retriever,
    expand_query,
    reciprocal_rank_fusion,
)

# ---------------------------------------------------------------------------
# RRF is deterministic (§7.7.3 test requirement)
# ---------------------------------------------------------------------------

class TestRRF:
    def test_rrf_deterministic(self) -> None:
        list1 = ["a", "b", "c"]
        list2 = ["b", "a", "d"]

        result1 = reciprocal_rank_fusion([list1, list2], k=60)
        result2 = reciprocal_rank_fusion([list1, list2], k=60)

        assert result1 == result2, "RRF must be deterministic"

    def test_rrf_higher_score_for_top_ranked(self) -> None:
        # Item appearing at rank 1 in both lists should beat item appearing at rank 3
        result = reciprocal_rank_fusion([["x", "y"], ["x", "z"]], k=60)
        scores = dict(result)
        assert scores["x"] > scores["y"], "x appears first in both lists"

    def test_rrf_empty_lists(self) -> None:
        result = reciprocal_rank_fusion([], k=60)
        assert result == []

    def test_rrf_single_list(self) -> None:
        result = reciprocal_rank_fusion([["a", "b", "c"]], k=60)
        ids = [item_id for item_id, _ in result]
        assert ids == ["a", "b", "c"]

    def test_rrf_returns_sorted_descending(self) -> None:
        result = reciprocal_rank_fusion([["a", "b"], ["b", "a"]], k=60)
        scores = [s for _, s in result]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_k_parameter_affects_scores(self) -> None:
        r1 = reciprocal_rank_fusion([["a", "b"]], k=10)
        r2 = reciprocal_rank_fusion([["a", "b"]], k=60)
        scores1 = dict(r1)
        scores2 = dict(r2)
        # With smaller k, rank differences are amplified
        assert scores1["a"] != scores2["a"]

    def test_rrf_union_of_all_ids(self) -> None:
        result = reciprocal_rank_fusion([["a", "b"], ["c", "d"]], k=60)
        ids = {item_id for item_id, _ in result}
        assert ids == {"a", "b", "c", "d"}


# ---------------------------------------------------------------------------
# Query expansion
# ---------------------------------------------------------------------------

class TestQueryExpansion:
    def test_returns_at_least_one_variant(self) -> None:
        variants = expand_query("determinante de matriz")
        assert len(variants) >= 1
        assert "determinante de matriz" in variants[0]

    def test_short_query_gets_expanded(self) -> None:
        variants = expand_query("álgebra")
        assert len(variants) >= 1

    def test_long_query_not_over_expanded(self) -> None:
        long_q = " ".join(["palavra"] * 20)
        variants = expand_query(long_q)
        assert len(variants) <= 2


# ---------------------------------------------------------------------------
# Output contract — §25.1
# ---------------------------------------------------------------------------

class TestRetrievalContract:
    def test_retrieval_result_shape(self) -> None:
        result = RetrievalResult(
            question_id="q-1",
            query="test",
            hits=[
                RetrievalHit(
                    chunk_id="c-1",
                    document_id="d-1",
                    score=0.9,
                    text="Some text",
                    page=1,
                    source="Doc A",
                ),
            ],
        )
        assert result.question_id == "q-1"
        assert len(result.hits) == 1
        assert result.hits[0].chunk_id == "c-1"
        assert result.hits[0].document_id == "d-1"
        assert isinstance(result.hits[0].score, float)
        assert isinstance(result.hits[0].text, str)

    def test_hit_fields_are_all_present(self) -> None:
        hit = RetrievalHit(
            chunk_id="c-2",
            document_id="d-2",
            score=0.5,
            text="content",
            page=None,
            source="source",
        )
        assert hit.chunk_id
        assert hit.document_id
        assert hit.source is not None


# ---------------------------------------------------------------------------
# Fake embedding integration
# ---------------------------------------------------------------------------

class TestFakeEmbeddingRetriever:
    @pytest.mark.asyncio
    async def test_embed_query_deterministic(self) -> None:
        provider = FakeEmbeddingProvider(dimension=16)
        v1 = await provider.embed_query("hello world")
        v2 = await provider.embed_query("hello world")
        assert v1 == v2

    @pytest.mark.asyncio
    async def test_embed_documents_batch(self) -> None:
        provider = FakeEmbeddingProvider(dimension=32)
        texts = ["text one", "text two", "text three"]
        vectors = await provider.embed_documents(texts)
        assert len(vectors) == 3
        assert all(len(v) == 32 for v in vectors)

    @pytest.mark.asyncio
    async def test_different_texts_different_vectors(self) -> None:
        provider = FakeEmbeddingProvider(dimension=64)
        v1 = await provider.embed_query("mathematics algebra")
        v2 = await provider.embed_query("chemistry organic")
        assert v1 != v2

    def test_build_retriever_factory(self) -> None:
        provider = FakeEmbeddingProvider()
        retriever = build_retriever(provider, top_k=5, rrf_k=30)
        assert isinstance(retriever, HybridRetriever)
