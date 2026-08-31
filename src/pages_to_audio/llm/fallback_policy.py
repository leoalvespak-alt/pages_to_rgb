"""LLM provider fallback policy — §27.3, §59.

Fallback to DeepSeek is triggered ONLY by technical failures:
  - timeout after retry budget exhausted
  - persistent 429 (rate limit)
  - persistent 5xx (server error)
  - provider unavailable
  - schema invalid after repair retry

§27.3 critical rule: solver ≠ verifier answer divergence does NOT trigger fallback.
Divergence triggers the Arbiter (§31). This is enforced by classify_error() returning
None for any non-technical exception.

Full chain (§59):
  Opus -> [retry x max_retries] -> schema repair -> DeepSeek -> FAILED
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


class FallbackTrigger(StrEnum):
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    SERVER_ERROR = "server_error"
    UNAVAILABLE = "unavailable"
    SCHEMA_INVALID = "schema_invalid"


_RETRYABLE_TRIGGERS: dict[str, FallbackTrigger] = {
    ReasonCode.LLM_TIMEOUT: FallbackTrigger.TIMEOUT,
    ReasonCode.LLM_RATE_LIMITED: FallbackTrigger.RATE_LIMITED,
    ReasonCode.LLM_PROVIDER_ERROR: FallbackTrigger.SERVER_ERROR,
}

_NONRETRYABLE_TRIGGERS: dict[str, FallbackTrigger] = {
    ReasonCode.LLM_SCHEMA_INVALID: FallbackTrigger.SCHEMA_INVALID,
    ReasonCode.LLM_SCHEMA_REPAIR_FAILED: FallbackTrigger.SCHEMA_INVALID,
    ReasonCode.LLM_ALL_PROVIDERS_FAILED: FallbackTrigger.UNAVAILABLE,
}


def classify_error(exc: Exception) -> FallbackTrigger | None:
    """Map exception → FallbackTrigger, or None if not a fallback condition.

    Returning None means the exception propagates (not a technical failure).
    Answer disagreement is deliberately not handled here.
    """
    if isinstance(exc, RetryableError):
        return _RETRYABLE_TRIGGERS.get(exc.reason_code)
    if isinstance(exc, NonRetryableError):
        return _NONRETRYABLE_TRIGGERS.get(exc.reason_code)
    return None


async def run_with_fallback[T](
    primary_fn: Callable[[], Awaitable[T]],
    fallback_fn: Callable[[], Awaitable[T]],
    *,
    max_retries: int = 2,
    context: str = "",
) -> tuple[T, str]:
    """Execute primary with retries, then fall back to secondary provider.

    Returns (result, provider_name) — provider_name is "anthropic" or "deepseek".
    Raises NonRetryableError(LLM_ALL_PROVIDERS_FAILED) if both fail.
    """
    last_exc: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            result = await primary_fn()
            if attempt > 0:
                logger.info("llm_primary_recovered", attempt=attempt, context=context)
            return result, "anthropic"
        except Exception as exc:
            trigger = classify_error(exc)
            if trigger is None:
                raise
            last_exc = exc
            logger.warning(
                "llm_primary_attempt_failed",
                attempt=attempt,
                max_retries=max_retries,
                trigger=str(trigger),
                error=str(exc),
                context=context,
            )

    logger.warning(
        "llm_fallback_activated",
        primary_attempts=max_retries + 1,
        last_error=str(last_exc),
        context=context,
    )
    try:
        result = await fallback_fn()
        return result, "deepseek"
    except Exception as exc:
        raise NonRetryableError(
            f"All LLM providers failed (context={context!r}): {exc}",
            reason_code=ReasonCode.LLM_ALL_PROVIDERS_FAILED,
        ) from exc
