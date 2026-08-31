"""Azure Cognitive Services TTS provider — §35, §9.2.2.

Fallback TTS provider when Google fails.
Uses Azure Speech Services REST API (no SDK required).
Timeout: 60s. Returns MP3 audio.
"""

from __future__ import annotations

import httpx

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.domain.ports.tts import TTSRequest, TTSSegment
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_TIMEOUT_S = 60.0
PROVIDER_NAME = "azure"


class AzureTTSProvider:
    """Azure Cognitive Services Text-to-Speech via REST."""

    def __init__(self, settings: AppSettings | None = None) -> None:
        cfg = settings or get_settings()
        self._key = cfg.AZURE_SPEECH_KEY.get_secret_value()
        self._region = cfg.AZURE_SPEECH_REGION

    def _api_url(self) -> str:
        return f"https://{self._region}.tts.speech.microsoft.com/cognitiveservices/v1"

    def _headers(self) -> dict[str, str]:
        return {
            "Ocp-Apim-Subscription-Key": self._key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3",
        }

    def _build_ssml(self, request: TTSRequest) -> str:
        voice = request.voice_name or "pt-BR-FranciscaNeural"
        rate_pct = f"{int((request.speaking_rate - 1.0) * 100):+d}%"
        return (
            f'<speak version="1.0" xml:lang="{request.language_code}">'
            f'<voice name="{voice}">'
            f'<prosody rate="{rate_pct}">{request.text}</prosody>'
            f"</voice></speak>"
        )

    async def synthesize(self, request: TTSRequest) -> TTSSegment:
        if not self._key or not self._region:
            raise NonRetryableError(
                "Azure TTS credentials not configured",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            )

        ssml = self._build_ssml(request)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
                resp = await client.post(
                    self._api_url(), headers=self._headers(), content=ssml.encode()
                )
        except httpx.TimeoutException as exc:
            raise RetryableError(
                f"Azure TTS timeout after {_TIMEOUT_S}s",
                reason_code=ReasonCode.TTS_TIMEOUT,
            ) from exc
        except httpx.HTTPError as exc:
            raise RetryableError(
                f"Azure TTS network error: {exc}",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            ) from exc

        if resp.status_code == 429:
            raise RetryableError(
                "Azure TTS rate limited", reason_code=ReasonCode.TTS_PROVIDER_FAILED
            )
        if resp.status_code >= 500:
            raise RetryableError(
                f"Azure TTS server error {resp.status_code}",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            )
        if resp.status_code >= 400:
            raise NonRetryableError(
                f"Azure TTS client error {resp.status_code}",
                reason_code=ReasonCode.TTS_PROVIDER_FAILED,
            )

        audio_data = resp.content
        duration = len(audio_data) / (128_000 / 8) if audio_data else 0.0
        logger.info(
            "azure_tts_synthesized",
            text_len=len(request.text),
            duration_s=round(duration, 2),
        )
        return TTSSegment(
            audio_data=audio_data,
            duration_seconds=duration,
            provider=PROVIDER_NAME,
        )
