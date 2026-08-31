"""OpenAI-compatible embedding provider — §24.3.

Works with OpenAI and any API that uses the same /embeddings endpoint shape,
including Azure OpenAI, local OpenAI-compatible servers, etc.
"""

from __future__ import annotations

from typing import Any

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT_S = 60.0
_BATCH_SIZE = 100


class OpenAIEmbeddingProvider:
    """Embeds texts using the OpenAI /v1/embeddings endpoint.

    Configurable base URL for OpenAI-compatible alternative providers.
    """

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        self._api_key = cfg.OPENAI_API_KEY.get_secret_value()
        self._base_url = cfg.OPENAI_API_BASE.rstrip("/")
        self._model = cfg.EMBEDDING_MODEL
        self._dim = cfg.EMBEDDING_DIMENSION
        self.model_name = self._model

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts. Auto-batches to avoid request limits."""
        all_vectors: list[list[float]] = []
        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            vectors = await self._embed_batch(batch)
            all_vectors.extend(vectors)
        return all_vectors

    async def embed_query(self, text: str) -> list[float]:
        vectors = await self._embed_batch([text])
        return vectors[0]

    async def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not self._api_key:
            raise NonRetryableError(
                "OpenAI API key not configured",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_AUTH_ERROR,
            )

        payload: dict[str, Any] = {"input": texts, "model": self._model}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(
                    f"{self._base_url}/embeddings",
                    json=payload,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            raise RetryableError(
                "OpenAI embedding timeout",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"OpenAI embedding HTTP error: {exc}",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_ERROR,
            ) from exc

        if resp.status_code == 401:
            raise NonRetryableError(
                "OpenAI embedding auth error",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_AUTH_ERROR,
            )
        if resp.status_code == 429:
            raise RetryableError(
                "OpenAI embedding rate limited",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_ERROR,
            )
        if resp.status_code >= 500:
            raise RetryableError(
                f"OpenAI embedding server error: {resp.status_code}",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_ERROR,
            )
        if resp.status_code >= 400:
            raise NonRetryableError(
                f"OpenAI embedding client error: {resp.status_code}",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_ERROR,
            )

        try:
            data = resp.json()
            return [item["embedding"] for item in sorted(data["data"], key=lambda x: x["index"])]
        except Exception as exc:
            raise NonRetryableError(
                f"OpenAI embedding invalid response: {exc}",
                reason_code=ReasonCode.EMBEDDING_PROVIDER_ERROR,
            ) from exc
