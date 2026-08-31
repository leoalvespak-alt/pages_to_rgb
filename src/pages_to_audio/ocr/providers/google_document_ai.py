"""Google Document AI OCR provider — §19.1, §5.4.1."""

from __future__ import annotations

from typing import Any

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.domain.ports.ocr import NormalizedOCRResult, OCRRequest
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.policies import OCR_GOOGLE_TIMEOUT_S

logger = get_logger(__name__)

_CONFIDENCE_THRESHOLD = 0.60


class GoogleDocumentAIProvider:
    """OCR via Google Document AI REST API."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        self._project = cfg.GOOGLE_DOCUMENT_AI_PROJECT_ID
        self._location = cfg.GOOGLE_DOCUMENT_AI_LOCATION
        self._processor = cfg.GOOGLE_DOCUMENT_AI_PROCESSOR_ID
        self._creds_file = cfg.GOOGLE_APPLICATION_CREDENTIALS
        self._endpoint = (
            f"https://{self._location}-documentai.googleapis.com/v1/projects/"
            f"{self._project}/locations/{self._location}/processors/"
            f"{self._processor}:process"
        )

    async def _get_access_token(self) -> str:
        import google.auth
        import google.auth.transport.requests

        creds, _ = google.auth.load_credentials_from_file(
            self._creds_file,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        request = google.auth.transport.requests.Request()
        creds.refresh(request)
        return str(creds.token)

    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult:
        try:
            token = await self._get_access_token()
        except Exception as exc:
            raise NonRetryableError(
                f"Google DocumentAI credentials error: {exc}",
                reason_code=ReasonCode.OCR_PROVIDER_AUTH_ERROR,
            ) from exc

        # Read image bytes from storage key (simplified — real impl uses StoragePort)
        image_bytes = b""  # TODO: inject StoragePort in Phase 5 integration
        encoded = __import__("base64").b64encode(image_bytes).decode()

        payload = {
            "rawDocument": {"mimeType": "image/jpeg", "content": encoded},
            "fieldMask": "text,pages",
        }
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=OCR_GOOGLE_TIMEOUT_S) as client:
                resp = await client.post(self._endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise RetryableError(
                "Google DocumentAI timeout",
                reason_code=ReasonCode.OCR_PROVIDER_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"Google DocumentAI HTTP error: {exc}",
                reason_code=ReasonCode.OCR_PROVIDER_ERROR,
            ) from exc

        if resp.status_code == 429:
            raise RetryableError(
                "Google DocumentAI rate limited",
                reason_code=ReasonCode.OCR_PROVIDER_RATE_LIMITED,
            )
        if resp.status_code >= 500:
            raise RetryableError(
                f"Google DocumentAI server error: {resp.status_code}",
                reason_code=ReasonCode.OCR_PROVIDER_ERROR,
            )
        if resp.status_code >= 400:
            raise NonRetryableError(
                f"Google DocumentAI client error: {resp.status_code} {resp.text[:200]}",
                reason_code=ReasonCode.OCR_INVALID_REQUEST,
            )

        try:
            data: dict[str, Any] = resp.json()
            return self._normalize(data, request)
        except Exception as exc:
            raise NonRetryableError(
                f"Google DocumentAI invalid response schema: {exc}",
                reason_code=ReasonCode.OCR_INVALID_RESPONSE,
            ) from exc

    def _normalize(self, data: dict[str, Any], request: OCRRequest) -> NormalizedOCRResult:
        text = data.get("document", {}).get("text", "")
        pages = data.get("document", {}).get("pages", [])
        blocks = []
        lines_out = []
        tokens_out = []
        confidence_sum = 0.0
        confidence_count = 0

        for page in pages:
            for block in page.get("blocks", []):
                conf = block.get("layout", {}).get("confidence", 0.0)
                confidence_sum += conf
                confidence_count += 1
                blocks.append({"text": "", "confidence": conf, "raw": block})
            for line in page.get("lines", []):
                lines_out.append({"raw": line})
            for token in page.get("tokens", []):
                tokens_out.append({"raw": token})

        avg_confidence = confidence_sum / confidence_count if confidence_count else 0.0

        return NormalizedOCRResult(
            text=text,
            blocks=blocks,
            lines=lines_out,
            tokens=tokens_out,
            reading_order=list(range(len(blocks))),
            tables=[],
            formulas=[],
            confidence=avg_confidence,
            raw_storage_key=f"sessions/unknown/ocr/google/{request.page_index}.json",
            provider="google_document_ai",
            model=None,
        )
