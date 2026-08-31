"""OCR selection policy, circuit breaker, and fallback chain — §5.5, §19.2, §41."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from src.pages_to_audio.common.errors import ReasonCode, RetryableError
from src.pages_to_audio.domain.ports.ocr import NormalizedOCRResult, OCRProvider, OCRRequest
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

# Minimum acceptable confidence — below this, try secondary provider
LOW_CONFIDENCE_THRESHOLD = 0.60

# Circuit breaker settings (§41)
CIRCUIT_BREAKER_FAILURE_THRESHOLD = 5
CIRCUIT_BREAKER_HALF_OPEN_AFTER_S = 60.0


class CircuitBreakerOpen(RetryableError):  # noqa: N818
    pass


@dataclass
class _CircuitBreakerState:
    failures: deque[float] = field(default_factory=lambda: deque(maxlen=20))
    opened_at: float | None = None

    def record_failure(self) -> None:
        self.failures.append(time.monotonic())

    def record_success(self) -> None:
        self.failures.clear()
        self.opened_at = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            recent = [t for t in self.failures if time.monotonic() - t < 60]
            if len(recent) >= CIRCUIT_BREAKER_FAILURE_THRESHOLD:
                self.opened_at = time.monotonic()
                logger.warning("circuit_breaker_opened")
            return self.opened_at is not None
        if time.monotonic() - self.opened_at >= CIRCUIT_BREAKER_HALF_OPEN_AFTER_S:
            logger.info("circuit_breaker_half_open")
            return False
        return True


class OCRPolicy:
    """
    Orchestrates OCR fallback chain (§5.5, §19.2, §59):
    Google → retry → Azure → failed

    Each provider has an independent circuit breaker (§41).
    Every provider switch generates an audit-ready event (§5.5.4).
    """

    def __init__(
        self,
        primary: OCRProvider,
        fallback: OCRProvider | None = None,
        *,
        confidence_threshold: float = LOW_CONFIDENCE_THRESHOLD,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._confidence = confidence_threshold
        self._cb_primary: _CircuitBreakerState = _CircuitBreakerState()
        self._cb_fallback: _CircuitBreakerState = _CircuitBreakerState()
        self.last_provider_used: str = ""
        self.fallback_triggered: bool = False
        self.events: list[dict[str, Any]] = []

    def _emit(self, event_type: str, **kwargs: Any) -> None:
        ev = {"event_type": event_type, "ts": time.monotonic(), **kwargs}
        self.events.append(ev)
        logger.info(event_type, **{k: v for k, v in kwargs.items() if k != "ts"})

    async def _try_provider(
        self,
        provider: OCRProvider,
        cb: _CircuitBreakerState,
        request: OCRRequest,
        provider_name: str,
    ) -> NormalizedOCRResult | None:
        if cb.is_open():
            self._emit("circuit_breaker_skip", provider=provider_name)
            raise CircuitBreakerOpen(
                f"Circuit breaker open for {provider_name}",
                reason_code=ReasonCode.OCR_CIRCUIT_BREAKER_OPEN,
            )
        try:
            result = await provider.analyze_page(request)
            cb.record_success()
            self.last_provider_used = provider_name
            return result
        except Exception as exc:
            cb.record_failure()
            self._emit("ocr_provider_failed", provider=provider_name, error=str(exc))
            raise

    async def analyze_page(self, request: OCRRequest) -> NormalizedOCRResult:
        # Try primary
        primary_result: NormalizedOCRResult | None = None
        primary_error: Exception | None = None

        try:
            primary_result = await self._try_provider(
                self._primary, self._cb_primary, request, "primary"
            )
        except Exception as exc:
            primary_error = exc

        if primary_result is not None:
            # Low confidence → try secondary for comparison (§5.5.2)
            if primary_result.confidence < self._confidence and self._fallback is not None:
                self._emit(
                    "ocr_low_confidence_fallback",
                    provider="primary",
                    confidence=primary_result.confidence,
                )
                try:
                    fallback_result = await self._try_provider(
                        self._fallback, self._cb_fallback, request, "fallback"
                    )
                    self.fallback_triggered = True
                    return fallback_result
                except Exception:
                    return primary_result
            return primary_result

        # Primary failed — try fallback
        if self._fallback is None:
            assert primary_error is not None
            raise primary_error

        self._emit("ocr_primary_failed_using_fallback")
        self.fallback_triggered = True
        try:
            return await self._try_provider(self._fallback, self._cb_fallback, request, "fallback")
        except Exception as fallback_exc:
            # Both failed
            raise RetryableError(
                "All OCR providers failed",
                reason_code=ReasonCode.OCR_ALL_PROVIDERS_FAILED,
            ) from fallback_exc
