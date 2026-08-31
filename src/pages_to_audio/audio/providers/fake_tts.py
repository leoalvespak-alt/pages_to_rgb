"""Fake TTS provider for tests — §9.2.4.

Generates silence audio with duration proportional to text length.
Deterministic: same text always produces the same bytes.
Uses WAV header (PCM silence) so duration can be calculated without FFmpeg.
"""

from __future__ import annotations

import hashlib
import struct

from src.pages_to_audio.domain.ports.tts import TTSRequest, TTSSegment

SAMPLE_RATE = 8000
CHANNELS = 1
BITS_PER_SAMPLE = 16
BYTES_PER_SECOND = SAMPLE_RATE * CHANNELS * (BITS_PER_SAMPLE // 8)
CHARS_PER_SECOND = 15.0


def _make_wav_silence(duration_seconds: float) -> bytes:
    """Generate a valid minimal PCM WAV file of silence."""
    num_samples = int(SAMPLE_RATE * duration_seconds)
    pcm_data = b"\x00" * (num_samples * CHANNELS * (BITS_PER_SAMPLE // 8))
    data_size = len(pcm_data)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + data_size,
        b"WAVE",
        b"fmt ",
        16,
        1,
        CHANNELS,
        SAMPLE_RATE,
        BYTES_PER_SECOND,
        CHANNELS * (BITS_PER_SAMPLE // 8),
        BITS_PER_SAMPLE,
        b"data",
        data_size,
    )
    return header + pcm_data


class FakeTTSProvider:
    """Deterministic fake TTS — generates silence proportional to text length."""

    PROVIDER_NAME = "fake"

    async def synthesize(self, request: TTSRequest) -> TTSSegment:
        duration = max(0.5, len(request.text) / CHARS_PER_SECOND)
        audio_data = _make_wav_silence(duration)
        return TTSSegment(
            audio_data=audio_data,
            duration_seconds=duration,
            provider=self.PROVIDER_NAME,
        )

    def fingerprint(self, text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()[:16]
