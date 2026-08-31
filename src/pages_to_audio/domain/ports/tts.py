"""TTS port — §35."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class TTSRequest:
    text: str
    language_code: str = "pt-BR"
    speaking_rate: float = 1.0
    voice_name: str = ""


@dataclass
class TTSSegment:
    audio_data: bytes
    duration_seconds: float
    provider: str


class TTSProvider(Protocol):
    async def synthesize(self, request: TTSRequest) -> TTSSegment: ...
