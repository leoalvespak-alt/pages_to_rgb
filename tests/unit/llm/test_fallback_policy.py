"""Tests for LLM fallback policy — §27.3, §59, §8.5.2."""

from __future__ import annotations

import pytest

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.llm.fallback_policy import (
    FallbackTrigger,
    classify_error,
    run_with_fallback,
)


class TestClassifyError:
    def test_timeout_is_fallback_trigger(self) -> None:
        exc = RetryableError("timed out", reason_code=ReasonCode.LLM_TIMEOUT)
        assert classify_error(exc) == FallbackTrigger.TIMEOUT

    def test_rate_limited_is_fallback_trigger(self) -> None:
        exc = RetryableError("429", reason_code=ReasonCode.LLM_RATE_LIMITED)
        assert classify_error(exc) == FallbackTrigger.RATE_LIMITED

    def test_provider_error_is_fallback_trigger(self) -> None:
        exc = RetryableError("5xx", reason_code=ReasonCode.LLM_PROVIDER_ERROR)
        assert classify_error(exc) == FallbackTrigger.SERVER_ERROR

    def test_schema_invalid_is_fallback_trigger(self) -> None:
        exc = NonRetryableError("bad json", reason_code=ReasonCode.LLM_SCHEMA_INVALID)
        assert classify_error(exc) == FallbackTrigger.SCHEMA_INVALID

    def test_unrelated_error_returns_none(self) -> None:
        exc = ValueError("some internal error")
        assert classify_error(exc) is None

    def test_answer_disagreement_is_not_a_trigger(self) -> None:
        # §27.3: divergence between Solver and Verifier does NOT trigger fallback
        # This would manifest as a plain ValueError or a custom non-LLM error
        exc = ValueError("solver=A verifier=B")
        assert classify_error(exc) is None

    def test_non_llm_retryable_is_none(self) -> None:
        exc = RetryableError("ocr failed", reason_code=ReasonCode.OCR_PROVIDER_ERROR)
        assert classify_error(exc) is None


class TestRunWithFallback:
    @pytest.mark.asyncio
    async def test_primary_succeeds(self) -> None:
        async def primary() -> str:
            return "primary_result"

        async def fallback() -> str:
            return "fallback_result"

        result, provider = await run_with_fallback(primary, fallback)
        assert result == "primary_result"
        assert provider == "anthropic"

    @pytest.mark.asyncio
    async def test_primary_timeout_triggers_fallback(self) -> None:
        async def primary() -> str:
            raise RetryableError("timeout", reason_code=ReasonCode.LLM_TIMEOUT)

        async def fallback() -> str:
            return "fallback_result"

        result, provider = await run_with_fallback(primary, fallback, max_retries=0)
        assert result == "fallback_result"
        assert provider == "deepseek"

    @pytest.mark.asyncio
    async def test_primary_429_triggers_fallback(self) -> None:
        async def primary() -> str:
            raise RetryableError("rate limited", reason_code=ReasonCode.LLM_RATE_LIMITED)

        async def fallback() -> str:
            return "deepseek_ok"

        result, provider = await run_with_fallback(primary, fallback, max_retries=0)
        assert provider == "deepseek"

    @pytest.mark.asyncio
    async def test_primary_retries_before_fallback(self) -> None:
        call_count = 0

        async def primary() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise RetryableError("timeout", reason_code=ReasonCode.LLM_TIMEOUT)
            return "recovered"

        async def fallback() -> str:
            return "fallback"

        result, provider = await run_with_fallback(primary, fallback, max_retries=2)
        assert result == "recovered"
        assert provider == "anthropic"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_both_fail_raises_all_failed(self) -> None:
        async def primary() -> str:
            raise RetryableError("timeout", reason_code=ReasonCode.LLM_TIMEOUT)

        async def fallback() -> str:
            raise RetryableError("also timeout", reason_code=ReasonCode.LLM_TIMEOUT)

        with pytest.raises(NonRetryableError) as exc_info:
            await run_with_fallback(primary, fallback, max_retries=0)
        assert exc_info.value.reason_code == ReasonCode.LLM_ALL_PROVIDERS_FAILED

    @pytest.mark.asyncio
    async def test_non_trigger_error_propagates_without_fallback(self) -> None:
        async def primary() -> str:
            raise ValueError("internal logic error")

        async def fallback() -> str:
            return "should not be called"

        with pytest.raises(ValueError):
            await run_with_fallback(primary, fallback)

    @pytest.mark.asyncio
    async def test_answer_disagreement_does_not_trigger_fallback(self) -> None:
        # §8.5.2: proving disagreement doesn't use fallback
        disagreement_exc = ValueError("solver=A verifier=B")

        async def primary() -> str:
            raise disagreement_exc

        async def fallback() -> str:
            return "should not reach here"

        # classify_error returns None for ValueError → propagates, no fallback
        with pytest.raises(ValueError):
            await run_with_fallback(primary, fallback)
