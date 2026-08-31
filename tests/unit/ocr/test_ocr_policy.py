"""Unit tests for OCR policy and circuit breaker — §5.5, §41."""

from __future__ import annotations

import pytest

from src.pages_to_audio.common.errors import RetryableError
from src.pages_to_audio.domain.ports.ocr import OCRRequest
from src.pages_to_audio.ocr.policy import (
    CIRCUIT_BREAKER_FAILURE_THRESHOLD,
    OCRPolicy,
    _CircuitBreakerState,
)
from src.pages_to_audio.ocr.providers.fake import FakeOCRProvider


def _request() -> OCRRequest:
    return OCRRequest(original_storage_key="sessions/test/frames/c/0.jpg", page_index=0)


@pytest.mark.asyncio
async def test_primary_success() -> None:
    primary = FakeOCRProvider(fixed_text="Hello OCR")
    policy = OCRPolicy(primary=primary)
    result = await policy.analyze_page(_request())
    assert result.text == "Hello OCR"
    assert policy.last_provider_used == "primary"
    assert not policy.fallback_triggered


@pytest.mark.asyncio
async def test_primary_failure_fallback_succeeds() -> None:
    primary = FakeOCRProvider(simulate_server_error=True)
    fallback = FakeOCRProvider(fixed_text="Fallback OCR")
    policy = OCRPolicy(primary=primary, fallback=fallback)
    result = await policy.analyze_page(_request())
    assert result.text == "Fallback OCR"
    assert policy.fallback_triggered


@pytest.mark.asyncio
async def test_both_providers_fail_raises() -> None:
    primary = FakeOCRProvider(simulate_timeout=True)
    fallback = FakeOCRProvider(simulate_server_error=True)
    policy = OCRPolicy(primary=primary, fallback=fallback)
    with pytest.raises(RetryableError):
        await policy.analyze_page(_request())


@pytest.mark.asyncio
async def test_low_confidence_triggers_fallback() -> None:
    primary = FakeOCRProvider(simulate_low_confidence=True)
    fallback = FakeOCRProvider(fixed_text="High confidence fallback", confidence=0.95)
    policy = OCRPolicy(primary=primary, fallback=fallback, confidence_threshold=0.60)
    result = await policy.analyze_page(_request())
    assert result.text == "High confidence fallback"
    assert policy.fallback_triggered


@pytest.mark.asyncio
async def test_low_confidence_no_fallback_returns_primary() -> None:
    primary = FakeOCRProvider(simulate_low_confidence=True)
    policy = OCRPolicy(primary=primary, fallback=None, confidence_threshold=0.60)
    result = await policy.analyze_page(_request())
    assert result.confidence < 0.60


def test_circuit_breaker_opens_after_threshold() -> None:
    cb = _CircuitBreakerState()
    for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
        cb.record_failure()
    assert cb.is_open()


def test_circuit_breaker_clears_on_success() -> None:
    cb = _CircuitBreakerState()
    for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD):
        cb.record_failure()
    assert cb.is_open()
    cb.record_success()
    assert not cb.is_open()


@pytest.mark.asyncio
async def test_circuit_breaker_skips_open_provider() -> None:
    primary = FakeOCRProvider(simulate_server_error=True)
    fallback = FakeOCRProvider(fixed_text="After circuit")
    policy = OCRPolicy(primary=primary, fallback=fallback)

    # Exhaust the circuit breaker
    for _ in range(CIRCUIT_BREAKER_FAILURE_THRESHOLD + 1):
        try:
            await policy.analyze_page(_request())
        except Exception:
            pass

    # Now primary circuit is open — should skip straight to fallback
    result = await policy.analyze_page(_request())
    assert result.text == "After circuit"


@pytest.mark.asyncio
async def test_non_retryable_from_primary_propagates() -> None:
    primary = FakeOCRProvider(simulate_invalid_schema=True)
    policy = OCRPolicy(primary=primary)
    from src.pages_to_audio.common.errors import NonRetryableError
    with pytest.raises(NonRetryableError):
        await policy.analyze_page(_request())


def test_paddle_disabled_by_default() -> None:
    from src.pages_to_audio.common.errors import NonRetryableError
    from src.pages_to_audio.ocr.providers.paddle import PaddleOCRProvider
    with pytest.raises(NonRetryableError):
        PaddleOCRProvider()
