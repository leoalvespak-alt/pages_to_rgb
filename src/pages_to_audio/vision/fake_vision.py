"""Fake vision provider for tests — §6.3.4."""

from __future__ import annotations

import asyncio

from src.pages_to_audio.domain.ports.vision import VisionRequest, VisionResult


class FakeVisionProvider:
    def __init__(
        self,
        *,
        description: str = "Fake vision analysis result",
        confidence: float = 0.90,
    ) -> None:
        self.description = description
        self.confidence = confidence
        self.calls: list[VisionRequest] = []

    async def analyze_region(self, request: VisionRequest) -> VisionResult:
        self.calls.append(request)
        await asyncio.sleep(0)
        return VisionResult(
            description=self.description,
            structured_data={"analyzed": True, "key": request.storage_key},
            confidence=self.confidence,
            provider="fake_vision",
        )
