"""PaddleOCR provider — §19.2, §5.4.3.

Optional: PADDLE_OCR_ENABLED=false by default.
Supports two modes: local (disabled on small VPS) and remote HTTP worker.
Server continues functioning when this provider is disabled (CLAUDE.md rule 19).
"""

from __future__ import annotations

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.domain.ports.ocr import NormalizedOCRResult, OCRRequest
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


class PaddleOCRProvider:
    """PaddleOCR via remote HTTP worker — §5.4.3."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        if not cfg.PADDLE_OCR_ENABLED:
            raise NonRetryableError(
                "PaddleOCR is disabled (PADDLE_OCR_ENABLED=false)",
                reason_code=ReasonCode.OCR_PROVIDER_DISABLED,
            )
        self._remote_url = cfg.PADDLE_OCR_REMOTE_URL.rstrip("/")

    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult:
        payload = {
            "storage_key": request.original_storage_key,
            "page_index": request.page_index,
        }
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(f"{self._remote_url}/analyze", json=payload)
        except httpx.TimeoutException as exc:
            raise RetryableError(
                "PaddleOCR remote timeout",
                reason_code=ReasonCode.OCR_PROVIDER_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"PaddleOCR remote HTTP error: {exc}",
                reason_code=ReasonCode.OCR_PROVIDER_ERROR,
            ) from exc

        if resp.status_code >= 500:
            raise RetryableError(
                f"PaddleOCR remote server error: {resp.status_code}",
                reason_code=ReasonCode.OCR_PROVIDER_ERROR,
            )
        if resp.status_code >= 400:
            raise NonRetryableError(
                f"PaddleOCR remote client error: {resp.status_code}",
                reason_code=ReasonCode.OCR_INVALID_REQUEST,
            )

        try:
            data = resp.json()
            return NormalizedOCRResult(
                text=data.get("text", ""),
                blocks=data.get("blocks", []),
                lines=data.get("lines", []),
                tokens=data.get("tokens", []),
                reading_order=data.get("reading_order", []),
                tables=data.get("tables", []),
                formulas=data.get("formulas", []),
                confidence=float(data.get("confidence", 0.0)),
                raw_storage_key=f"sessions/unknown/ocr/paddle/{request.page_index}.json",
                provider="paddle_remote",
            )
        except Exception as exc:
            raise NonRetryableError(
                f"PaddleOCR remote invalid response: {exc}",
                reason_code=ReasonCode.OCR_INVALID_RESPONSE,
            ) from exc
