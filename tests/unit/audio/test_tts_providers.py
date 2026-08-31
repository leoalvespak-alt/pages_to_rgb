"""Tests for TTS providers — §9.2, §9.7.5."""

from __future__ import annotations

import pytest

from src.pages_to_audio.audio.providers.fake_tts import FakeTTSProvider
from src.pages_to_audio.domain.ports.tts import TTSRequest


class TestFakeTTSProvider:
    @pytest.mark.asyncio
    async def test_returns_audio_bytes(self) -> None:
        provider = FakeTTSProvider()
        request = TTSRequest(text="Questão 1. Letra B.", language_code="pt-BR")
        segment = await provider.synthesize(request)
        assert len(segment.audio_data) > 0

    @pytest.mark.asyncio
    async def test_duration_proportional_to_text(self) -> None:
        provider = FakeTTSProvider()
        short = await provider.synthesize(TTSRequest(text="A."))
        long = await provider.synthesize(TTSRequest(text="Questão 1. Letra B. " * 5))
        assert long.duration_seconds > short.duration_seconds

    @pytest.mark.asyncio
    async def test_minimum_duration(self) -> None:
        provider = FakeTTSProvider()
        seg = await provider.synthesize(TTSRequest(text="A"))
        assert seg.duration_seconds >= 0.5

    @pytest.mark.asyncio
    async def test_provider_name(self) -> None:
        provider = FakeTTSProvider()
        seg = await provider.synthesize(TTSRequest(text="Test text."))
        assert seg.provider == "fake"

    @pytest.mark.asyncio
    async def test_deterministic(self) -> None:
        provider = FakeTTSProvider()
        r = TTSRequest(text="Questão 5. Letra D.")
        s1 = await provider.synthesize(r)
        s2 = await provider.synthesize(r)
        assert s1.audio_data == s2.audio_data
        assert s1.duration_seconds == s2.duration_seconds

    @pytest.mark.asyncio
    async def test_wav_header_valid(self) -> None:
        provider = FakeTTSProvider()
        seg = await provider.synthesize(TTSRequest(text="Hello."))
        assert seg.audio_data[:4] == b"RIFF"
        assert seg.audio_data[8:12] == b"WAVE"
