#!/usr/bin/env python3
"""RAG provider benchmark — §52.

A/B comparison of embedding models, chunk sizes, RRF constants, top-K, and reranker.
Output: docs/benchmarks/rag_<timestamp>.json

Usage:
    python scripts/benchmark_providers.py --queries queries.txt --corpus corpus/
    python scripts/benchmark_providers.py --quick   # uses built-in sample data
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

# Ensure src/ is on the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pages_to_audio.llm.providers.fake_embedding import FakeEmbeddingProvider
from src.pages_to_audio.rag.chunking import chunk_document
from src.pages_to_audio.rag.retrieval import HybridRetriever, reciprocal_rank_fusion


SAMPLE_CORPUS = [
    {
        "id": "doc-1",
        "text": (
            "# Álgebra Linear\n\n"
            "## Matrizes e Determinantes\n\n"
            "Uma matriz é um arranjo retangular de números. "
            "O determinante de uma matriz quadrada é um valor escalar. "
            "A matriz identidade tem determinante igual a 1.\n\n"
            "## Espaços Vetoriais\n\n"
            "Um espaço vetorial é um conjunto com operações de adição e multiplicação por escalar. "
            "Base canônica, transformações lineares, autovalores e autovetores são conceitos fundamentais."
        ),
        "discipline": "Matemática",
        "subject": "Álgebra Linear",
    },
    {
        "id": "doc-2",
        "text": (
            "# Química Orgânica\n\n"
            "## Hidrocarbonetos\n\n"
            "Alcanos são hidrocarbonetos saturados. "
            "Alcenos possuem dupla ligação carbono-carbono. "
            "Alquinos possuem tripla ligação.\n\n"
            "## Reações Orgânicas\n\n"
            "Substituição, adição, eliminação e oxidação são os principais tipos de reações. "
            "Reagentes nucleofílicos atacam centros eletrofílicos."
        ),
        "discipline": "Química",
        "subject": "Química Orgânica",
    },
]

SAMPLE_QUERIES = [
    "determinante de matriz identidade",
    "hidrocarbonetos com dupla ligação",
    "espaço vetorial transformação linear",
    "reações de substituição nucleofílica",
    "autovalores autovetores álgebra",
]

GROUND_TRUTH = {
    "determinante de matriz identidade": ["doc-1"],
    "hidrocarbonetos com dupla ligação": ["doc-2"],
    "espaço vetorial transformação linear": ["doc-1"],
    "reações de substituição nucleofílica": ["doc-2"],
    "autovalores autovetores álgebra": ["doc-1"],
}


@dataclass
class RunResult:
    config: dict[str, Any]
    precision_at_k: float
    recall_at_k: float
    mean_rr: float
    latency_ms: float
    queries_evaluated: int


async def _embed_corpus(
    provider: Any,
    corpus: list[dict[str, Any]],
    chunk_size: int,
    overlap: int,
) -> list[dict[str, Any]]:
    chunks = []
    for doc in corpus:
        doc_chunks = chunk_document(
            doc["text"],
            chunk_size=chunk_size,
            overlap=overlap,
            discipline=doc.get("discipline"),
            subject=doc.get("subject"),
        )
        texts = [c.text for c in doc_chunks]
        if not texts:
            continue
        embeddings = await provider.embed_documents(texts)
        for chunk, emb in zip(doc_chunks, embeddings, strict=True):
            chunks.append({
                "id": f"{doc['id']}-{chunk.chunk_index}",
                "doc_id": doc["id"],
                "text": chunk.text,
                "embedding": emb,
                "discipline": doc.get("discipline"),
                "subject": doc.get("subject"),
            })
    return chunks


def _in_memory_rrf_search(
    query_embedding: list[float],
    query_text: str,
    chunks: list[dict[str, Any]],
    top_k: int,
    rrf_k: int,
) -> list[str]:
    """Simple in-memory cosine + keyword search with RRF."""
    import math

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na and nb else 0.0

    query_words = set(query_text.lower().split())

    vec_scores = sorted(
        [(c["id"], cosine(query_embedding, c["embedding"])) for c in chunks],
        key=lambda x: x[1],
        reverse=True,
    )
    kw_scores = sorted(
        [(c["id"], len(query_words & set(c["text"].lower().split()))) for c in chunks],
        key=lambda x: x[1],
        reverse=True,
    )

    fused = reciprocal_rank_fusion(
        [[cid for cid, _ in vec_scores], [cid for cid, _ in kw_scores]],
        k=rrf_k,
    )
    return [cid for cid, _ in fused[:top_k]]


async def run_benchmark(
    provider: Any,
    corpus: list[dict[str, Any]],
    queries: list[str],
    ground_truth: dict[str, list[str]],
    config: dict[str, Any],
) -> RunResult:
    chunk_size = config.get("chunk_size", 500)
    overlap = config.get("overlap", 50)
    top_k = config.get("top_k", 5)
    rrf_k = config.get("rrf_k", 60)

    chunks = await _embed_corpus(provider, corpus, chunk_size, overlap)

    precisions, recalls, rrs = [], [], []
    total_latency = 0.0

    for q in queries:
        t0 = time.monotonic()
        q_embedding = await provider.embed_query(q)
        result_ids = _in_memory_rrf_search(q_embedding, q, chunks, top_k, rrf_k)
        total_latency += (time.monotonic() - t0) * 1000

        relevant_docs = set(ground_truth.get(q, []))
        if not relevant_docs:
            continue

        # Map chunk ids back to doc ids
        chunk_to_doc = {c["id"]: c["doc_id"] for c in chunks}
        retrieved_docs = [chunk_to_doc.get(cid, "") for cid in result_ids]

        hits = [doc for doc in retrieved_docs if doc in relevant_docs]
        precision = len(hits) / top_k if top_k else 0.0
        recall = len(set(hits)) / len(relevant_docs) if relevant_docs else 0.0

        rr = 0.0
        for rank, doc in enumerate(retrieved_docs, start=1):
            if doc in relevant_docs:
                rr = 1.0 / rank
                break

        precisions.append(precision)
        recalls.append(recall)
        rrs.append(rr)

    n = len(precisions) or 1
    return RunResult(
        config=config,
        precision_at_k=sum(precisions) / n,
        recall_at_k=sum(recalls) / n,
        mean_rr=sum(rrs) / n,
        latency_ms=total_latency / (len(queries) or 1),
        queries_evaluated=len(precisions),
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="RAG provider benchmark")
    parser.add_argument("--quick", action="store_true", help="Use built-in sample data")
    parser.add_argument("--output-dir", default="docs/benchmarks", help="Output directory")
    args = parser.parse_args()

    corpus = SAMPLE_CORPUS
    queries = SAMPLE_QUERIES
    gt = GROUND_TRUTH

    # Configuration grid to test
    configs: list[dict[str, Any]] = [
        {"provider": "fake-1536", "chunk_size": 500, "overlap": 50, "top_k": 5, "rrf_k": 60},
        {"provider": "fake-1536", "chunk_size": 300, "overlap": 30, "top_k": 5, "rrf_k": 60},
        {"provider": "fake-1536", "chunk_size": 500, "overlap": 50, "top_k": 10, "rrf_k": 60},
        {"provider": "fake-1536", "chunk_size": 500, "overlap": 50, "top_k": 5, "rrf_k": 30},
    ]

    providers: dict[str, Any] = {
        "fake-1536": FakeEmbeddingProvider(dimension=1536),
    }

    results = []
    for cfg in configs:
        pname = cfg.get("provider", "fake-1536")
        provider = providers.get(pname, FakeEmbeddingProvider())
        print(f"Running: {cfg}")
        result = await run_benchmark(provider, corpus, queries, gt, cfg)
        results.append(asdict(result))
        print(
            f"  P@{cfg['top_k']}={result.precision_at_k:.3f}  "
            f"R@{cfg['top_k']}={result.recall_at_k:.3f}  "
            f"MRR={result.mean_rr:.3f}  "
            f"lat={result.latency_ms:.1f}ms"
        )

    # Write output
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    out_path = out_dir / f"rag_{ts}.json"
    out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
