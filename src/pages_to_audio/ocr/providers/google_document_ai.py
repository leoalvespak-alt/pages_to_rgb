"""Google Document AI OCR provider — §19.1, §5.4.1."""

from __future__ import annotations

from typing import Any

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.domain.ports.ocr import NormalizedOCRResult, OCRRequest
from src.pages_to_audio.domain.ports.storage import StoragePort
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.policies import OCR_GOOGLE_TIMEOUT_S

logger = get_logger(__name__)

_CONFIDENCE_THRESHOLD = 0.60


class GoogleDocumentAIProvider:
    """OCR via Google Document AI REST API."""

    def __init__(
        self,
        settings: AppSettings | None = None,
        storage: StoragePort | None = None,
        credentials_json: str | None = None,
        project_id: str | None = None,
        location: str | None = None,
        processor_id: str | None = None,
        processor_version: str | None = None,
    ) -> None:
        cfg = settings or get_settings()
        self._settings = cfg
        self._storage = storage
        self._project = project_id or cfg.GOOGLE_DOCUMENT_AI_PROJECT_ID
        self._location = location or cfg.GOOGLE_DOCUMENT_AI_LOCATION
        self._processor = processor_id or cfg.GOOGLE_DOCUMENT_AI_PROCESSOR_ID
        self._processor_version = processor_version
        self._creds_file = cfg.GOOGLE_APPLICATION_CREDENTIALS
        self._credentials_json = credentials_json
        self._bucket = cfg.R2_BUCKET_ORIGINALS
        processor_path = f"processors/{self._processor}"
        if self._processor_version:
            processor_path += f"/processorVersions/{self._processor_version}"
        self._endpoint = f"https://{self._location}-documentai.googleapis.com/v1/projects/{self._project}/locations/{self._location}/{processor_path}:process"

    async def _get_access_token(self) -> str:
        # S05.7: rotina compartilhada (JSON ou caminho) + refresh em thread com reuso.
        from src.pages_to_audio.ocr.credentials import (
            get_google_access_token,
            load_google_credentials,
        )

        creds = load_google_credentials(
            self._credentials_json, file_fallback=self._creds_file or None
        )
        return await get_google_access_token(creds)

    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult:
        try:
            token = await self._get_access_token()
        except Exception as exc:
            raise NonRetryableError(
                f"Google DocumentAI credentials error: {exc}",
                reason_code=ReasonCode.OCR_PROVIDER_AUTH_ERROR,
            ) from exc

        image_bytes_raw = request.hints.get("image_bytes")
        if isinstance(image_bytes_raw, (bytes, bytearray)):
            image_bytes = bytes(image_bytes_raw)
        else:
            if self._storage is None:
                from src.pages_to_audio.storage import get_storage_adapter

                self._storage = get_storage_adapter()
            image_bytes = await self._storage.get_object(self._bucket, request.original_storage_key)
        if not image_bytes:
            raise NonRetryableError(
                "Google DocumentAI received an empty image",
                reason_code=ReasonCode.OCR_INVALID_REQUEST,
            )
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
            result = self._normalize(data, request)
            # S05.8/A28: persiste artefato OCR bruto real sob a sessão correta
            # antes de anunciar sua chave (nunca sessions/unknown).
            raw_key = await self._persist_raw_artifact(request, data)
            from dataclasses import replace as _replace

            return _replace(result, raw_storage_key=raw_key)
        except (NonRetryableError, RetryableError):
            raise
        except Exception as exc:
            raise NonRetryableError(
                f"Google DocumentAI invalid response schema: {exc}",
                reason_code=ReasonCode.OCR_INVALID_RESPONSE,
            ) from exc

    def _normalize(self, data: dict[str, Any], request: OCRRequest) -> NormalizedOCRResult:
        document = data.get("document", {})
        text = str(document.get("text", ""))
        pages = document.get("pages", [])
        blocks: list[dict[str, Any]] = []
        lines_out: list[dict[str, Any]] = []
        tokens_out: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        formulas: list[dict[str, Any]] = []
        quality_metrics: dict[str, Any] = {}
        confidence_sum = 0.0
        confidence_count = 0

        for page in pages:
            quality = page.get("imageQualityScores")
            if isinstance(quality, dict):
                quality_metrics.update(quality)
            for block in page.get("blocks", []):
                layout = block.get("layout", {})
                conf = float(layout.get("confidence", 0.0) or 0.0)
                if conf:
                    confidence_sum += conf
                    confidence_count += 1
                blocks.append(
                    {
                        "text": self._anchor_text(layout.get("textAnchor"), text),
                        "confidence": conf,
                        "raw": block,
                    }
                )
            for line in page.get("lines", []):
                layout = line.get("layout", {})
                conf = float(layout.get("confidence", 0.0) or 0.0)
                if conf:
                    confidence_sum += conf
                    confidence_count += 1
                lines_out.append(
                    {
                        "text": self._anchor_text(layout.get("textAnchor"), text),
                        "confidence": conf,
                        "raw": line,
                    }
                )
            for token in page.get("tokens", []):
                layout = token.get("layout", {})
                conf = float(layout.get("confidence", 0.0) or 0.0)
                if conf:
                    confidence_sum += conf
                    confidence_count += 1
                tokens_out.append(
                    {
                        "text": self._anchor_text(layout.get("textAnchor"), text),
                        "confidence": conf,
                        "raw": token,
                    }
                )
            tables.extend(page.get("tables", []))
            formulas.extend(page.get("formulas", []))

        avg_confidence = confidence_sum / confidence_count if confidence_count else 0.0

        session_hint = str(request.hints.get("session_public_id") or "pending")
        return NormalizedOCRResult(
            text=text,
            blocks=blocks,
            lines=lines_out,
            tokens=tokens_out,
            reading_order=list(range(len(blocks))),
            tables=tables,
            formulas=formulas,
            confidence=avg_confidence,
            raw_storage_key=f"sessions/{session_hint}/ocr/google/{request.page_index}.json",
            provider="google_document_ai",
            model="OCR_PROCESSOR",
            quality_metrics=quality_metrics,
        )

    async def _persist_raw_artifact(self, request: OCRRequest, data: dict[str, Any]) -> str:
        """S05.8: grava JSON bruto e retorna chave real (sessão correta)."""
        import json as _json

        from src.pages_to_audio.storage.keys import ocr_raw_key

        session_hint = str(request.hints.get("session_public_id") or "pending")
        key = ocr_raw_key(session_hint, "google", request.page_index)
        storage = self._storage
        if storage is None:
            from src.pages_to_audio.storage import get_storage_adapter

            storage = get_storage_adapter()
            self._storage = storage
        raw = _json.dumps(data, ensure_ascii=False).encode("utf-8")
        await storage.put_object(
            "ocr-raw",
            key,
            raw,
            "application/json",
            sha256=__import__("hashlib").sha256(raw).hexdigest(),
            overwrite=True,
        )
        return key

    @staticmethod
    def _anchor_text(anchor: Any, document_text: str) -> str:
        if not isinstance(anchor, dict):
            return ""
        chunks: list[str] = []
        for segment in anchor.get("textSegments", []):
            if not isinstance(segment, dict):
                continue
            try:
                start = int(segment.get("startIndex", 0))
                end = int(segment.get("endIndex", start))
            except (TypeError, ValueError):
                continue
            chunks.append(document_text[max(0, start) : max(start, end)])
        return "".join(chunks)
