"""Fake (deterministic) embedding provider for tests — §24.3."""

from __future__ import annotations

import hashlib
import math


class FakeEmbeddingProvider:
    """Deterministic embeddings: hash the text into a unit vector.

    The same text always produces the same vector.
    Dimension defaults to 1536 to match the schema default.
    """

    def __init__(self, dimension: int = 1536, model: str = "fake-v1") -> None:
        self._dim = dimension
        self.model_name = model

    def _text_to_vector(self, text: str) -> list[float]:
        # Hash text to a deterministic seed, then generate a unit vector
        h = hashlib.sha256(text.encode()).digest()
        # Use bytes in pairs as raw float components, wrap around
        vals: list[float] = []
        for i in range(self._dim):
            byte_idx = (i * 2) % len(h)
            raw = (h[byte_idx] << 8 | h[(byte_idx + 1) % len(h)]) / 65535.0
            vals.append(raw - 0.5)  # center around 0

        # Normalize to unit vector
        norm = math.sqrt(sum(v * v for v in vals)) or 1.0
        return [v / norm for v in vals]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._text_to_vector(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._text_to_vector(text)
