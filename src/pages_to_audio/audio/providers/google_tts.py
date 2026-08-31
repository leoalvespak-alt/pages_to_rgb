"""Google Cloud TTS provider — §35, §9.2.2.

Uses REST API via httpx (no SDK required).
Voice: pt-BR-Standard-A (configurable via settings — default for benchmarking).
Timeout: 60s per request (§42). Retry: caller via fallback_policy.
§9 DoD: supports pt-BR voices.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.domain.ports.tts import TTSRequest, TTSSegment
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_API_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"
_TIMEOUT_S = 60.0
PROVIDER_NAME = "google"


class GoogleTTSProvider:
    """Google Cloud Text-to-Speech via REST."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        self._credentials_path = cfg.GOOGLE_TTS_CREDENTIALS

    async def synthesize(self, request: TTSRequest) -> TTSSegment:
        token = await self._get_token()
        if not token:
            raise NonRetryableError(
                "Google TTS credentials not configured",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            )

        voice_name = request.voice_name or "pt-BR-Standard-A"
        body: dict[str, Any] = {
            "input": {"text": request.text},
            "voice": {
                "languageCode": request.language_code,
                "name": voice_name,
            },
            "audioConfig": {
                "audioEncoding": "MP3",
                "speakingRate": request.speaking_rate,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(
                    _API_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    json=body,
                )
        except httpx.TimeoutException as exc:
            raise RetryableError(
                f"Google TTS timeout after {_TIMEOUT_S}s",
                reason_code=ReasonCode.TTS_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"Google TTS network error: {exc}",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            ) from exc

        if resp.status_code == 429:
            raise RetryableError(
                "Google TTS rate limited", reason_code=ReasonCode.TTS_PROVIDER_FAILED
            )
        if resp.status_code >= 500:
            raise RetryableError(
                f"Google TTS server error {resp.status_code}",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            )
        if resp.status_code >= 400:
            raise NonRetryableError(
                f"Google TTS client error {resp.status_code}",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            )

        data = resp.json()
        audio_b64 = data.get("audioContent", "")
        audio_data = base64.b64decode(audio_b64) if audio_b64 else b""
        duration = len(audio_data) / (128_000 / 8) if audio_data else 0.0

        logger.info(
            "google_tts_synthesized",
            text_len=len(request.text),
            duration_s=round(duration, 2),
        )
        return TTSSegment(
            audio_data=audio_data,
            duration_seconds=duration,
            provider=PROVIDER_NAME,
        )

    async def _get_token(self) -> str:
        if not self._credentials_path:
            return ""
        try:
            import google.auth  # type: ignore[import-untyped]
            import google.auth.transport.requests  # type: ignore[import-untyped]

            creds, _ = google.auth.load_credentials_from_file(
                self._credentials_path,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            auth_req = google.auth.transport.requests.Request()
            creds.refresh(auth_req)
            return str(creds.token) if creds.token else ""
        except Exception as exc:
            raise NonRetryableError(
                f"Google TTS auth failed: {exc}",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            ) from exc
