"""Azure Document Intelligence OCR provider — §19.1, §5.4.2."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.domain.ports.ocr import NormalizedOCRResult, OCRRequest
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.policies import OCR_AZURE_TIMEOUT_S

logger = get_logger(__name__)


class AzureDocumentIntelligenceProvider:
    """OCR via Azure Document Intelligence REST API (v3.1)."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        endpoint = cfg.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT.rstrip("/")
        self._analyze_url = (
            f"{endpoint}/documentintelligence/documentModels/"
            "prebuilt-read:analyze?api-version=2024-02-29-preview"
        )
        self._key = cfg.AZURE_DOCUMENT_INTELLIGENCE_KEY.get_secret_value()

    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult:
        if not self._key:
            raise NonRetryableError(
                "Azure Document Intelligence key not configured",
                reason_code=ReasonCode.OCR_PROVIDER_AUTH_ERROR,
            )

        image_bytes = b""  # TODO: inject StoragePort in Phase 5 integration
        headers = {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "image/jpeg",
        }

        try:
            async with httpx.AsyncClient(timeout=OCR_AZURE_TIMEOUT_S) as client:
                resp = await client.post(self._analyze_url, content=image_bytes, headers=headers)
        except httpx.TimeoutException as exc:
            raise RetryableError(
                "Azure Document Intelligence timeout",
                reason_code=ReasonCode.OCR_PROVIDER_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"Azure Document Intelligence HTTP error: {exc}",
                reason_code=ReasonCode.OCR_PROVIDER_ERROR,
            ) from exc

        if resp.status_code == 429:
            raise RetryableError(
                "Azure Document Intelligence rate limited",
                reason_code=ReasonCode.OCR_PROVIDER_RATE_LIMITED,
            )
        if resp.status_code >= 500:
            raise RetryableError(
                f"Azure Document Intelligence server error: {resp.status_code}",
                reason_code=ReasonCode.OCR_PROVIDER_ERROR,
            )
        if resp.status_code not in (200, 202):
            raise NonRetryableError(
                f"Azure Document Intelligence client error: {resp.status_code}",
                reason_code=ReasonCode.OCR_INVALID_REQUEST,
            )

        # Async polling for 202 responses
        if resp.status_code == 202:
            operation_url = resp.headers.get("Operation-Location", "")
            data = await self._poll_result(operation_url)
        else:
            data = resp.json()

        try:
            return self._normalize(data, request)
        except Exception as exc:
            raise NonRetryableError(
                f"Azure Document Intelligence invalid response: {exc}",
                reason_code=ReasonCode.OCR_INVALID_RESPONSE,
            ) from exc

    async def _poll_result(self, operation_url: str) -> dict[str, Any]:
        deadline = time.monotonic() + OCR_AZURE_TIMEOUT_S
        async with httpx.AsyncClient(timeout=30) as client:
            while time.monotonic() < deadline:
                resp = await client.get(
                    operation_url,
                    headers={"Ocp-Apim-Subscription-Key": self._key},
                )
                data = resp.json()
                status = data.get("status", "")
                if status == "succeeded":
                    return data
                if status == "failed":
                    raise RetryableError(
                        "Azure Document Intelligence analysis failed",
                        reason_code=ReasonCode.OCR_PROVIDER_ERROR,
                    )
                await asyncio.sleep(2)
        raise RetryableError(
            "Azure Document Intelligence polling timeout",
            reason_code=ReasonCode.OCR_PROVIDER_TIMEOUT,
        )

    def _normalize(self, data: dict[str, Any], request: OCRRequest) -> NormalizedOCRResult:
        result = data.get("analyzeResult", data)
        text = result.get("content", "")
        pages_raw = result.get("pages", [])

        blocks, lines_out, tokens_out = [], [], []
        confidence_sum = 0.0
        confidence_count = 0

        for page in pages_raw:
            for line in page.get("lines", []):
                conf = line.get("confidence", 0.0)
                confidence_sum += conf
                confidence_count += 1
                lines_out.append({"text": line.get("content", ""), "confidence": conf})
            for word in page.get("words", []):
                tokens_out.append(
                    {
                        "text": word.get("content", ""),
                        "confidence": word.get("confidence", 0.0),
                    }
                )

        avg_conf = confidence_sum / confidence_count if confidence_count else 0.0

        return NormalizedOCRResult(
            text=text,
            blocks=blocks,
            lines=lines_out,
            tokens=tokens_out,
            reading_order=list(range(len(lines_out))),
            tables=[],
            formulas=[],
            confidence=avg_conf,
            raw_storage_key=f"sessions/unknown/ocr/azure/{request.page_index}.json",
            provider="azure_document_intelligence",
            model=None,
        )
