"""Fake OCR provider for tests — §5.4.5."""

from __future__ import annotations

import asyncio

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.domain.ports.ocr import NormalizedOCRResult, OCRRequest


class FakeOCRProvider:
    """Deterministic fake provider configurable for test scenarios."""

    def __init__(
        self,
        *,
        simulate_timeout: bool = False,
        simulate_server_error: bool = False,
        simulate_low_confidence: bool = False,
        simulate_invalid_schema: bool = False,
        fixed_text: str = "Fake OCR text",
        confidence: float = 0.95,
    ) -> None:
        self.simulate_timeout = simulate_timeout
        self.simulate_server_error = simulate_server_error
        self.simulate_low_confidence = simulate_low_confidence
        self.simulate_invalid_schema = simulate_invalid_schema
        self.fixed_text = fixed_text
        self.confidence = confidence
        self.calls: list[OCRRequest] = []

    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult:
        self.calls.append(request)

        if self.simulate_timeout:
            raise RetryableError(
                "Fake OCR timeout",
                reason_code=ReasonCode.OCR_PROVIDER_TIMEOUT,
            )
        if self.simulate_server_error:
            raise RetryableError(
                "Fake OCR 500",
                reason_code=ReasonCode.OCR_PROVIDER_ERROR,
            )
        if self.simulate_invalid_schema:
            raise NonRetryableError(
                "Fake OCR invalid schema",
                reason_code=ReasonCode.OCR_INVALID_RESPONSE,
            )

        await asyncio.sleep(0)

        conf = 0.45 if self.simulate_low_confidence else self.confidence

        return NormalizedOCRResult(
            text=self.fixed_text,
            blocks=[{"text": self.fixed_text, "confidence": conf}],
            lines=[{"text": self.fixed_text}],
            tokens=[],
            reading_order=[0],
            tables=[],
            formulas=[],
            confidence=conf,
            raw_storage_key=f"sessions/fake/ocr/fake/{request.page_index}.json",
            provider="fake",
            model=None,
        )
