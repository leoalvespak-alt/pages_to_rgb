"""Tests for Solver orchestration — §29, §8.7, §8.11."""

from __future__ import annotations

import pytest

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode, RetryableError
from src.pages_to_audio.llm.providers.fake_reasoning import FakeReasoningProvider
from src.pages_to_audio.llm.solver import solve_question

_ALTS = {"A": "Option A", "B": "Option B", "C": "Option C"}


class TestSolveQuestion:
    @pytest.mark.asyncio
    async def test_returns_answer_from_primary(self) -> None:
        primary = FakeReasoningProvider(default_answer="B")
        fallback = FakeReasoningProvider(default_answer="C")
        result, provider = await solve_question(
            1, "Question text", _ALTS, [], primary=primary, fallback=fallback
        )
        assert result.answer == "B"
        assert provider == "anthropic"

    @pytest.mark.asyncio
    async def test_falls_back_on_timeout(self) -> None:
        primary = FakeReasoningProvider(
            solve_error=RetryableError("timeout", reason_code=ReasonCode.LLM_TIMEOUT)
        )
        fallback = FakeReasoningProvider(default_answer="C")
        result, provider = await solve_question(
            1, "Q", _ALTS, [], primary=primary, fallback=fallback, max_retries=0
        )
        assert result.answer == "C"
        assert provider == "deepseek"

    @pytest.mark.asyncio
    async def test_uses_question_specific_answer(self) -> None:
        primary = FakeReasoningProvider(solve_overrides={5: "E"}, default_answer="A")
        fallback = FakeReasoningProvider(default_answer="A")
        result, provider = await solve_question(
            5, "Q5", {"A": "a", "B": "b", "C": "c", "D": "d", "E": "e"},
            [], primary=primary, fallback=fallback,
        )
        assert result.answer == "E"

    @pytest.mark.asyncio
    async def test_both_fail_raises(self) -> None:
        err = RetryableError("fail", reason_code=ReasonCode.LLM_TIMEOUT)
        primary = FakeReasoningProvider(solve_error=err)
        fallback = FakeReasoningProvider(solve_error=err)
        with pytest.raises(NonRetryableError) as exc_info:
            await solve_question(
                1, "Q", _ALTS, [], primary=primary, fallback=fallback, max_retries=0
            )
        assert exc_info.value.reason_code == ReasonCode.LLM_ALL_PROVIDERS_FAILED

    @pytest.mark.asyncio
    async def test_retries_primary_before_fallback(self) -> None:
        # Primary fails once then succeeds
        call_count = 0
        original_solve = FakeReasoningProvider.solve

        class OnceFailPrimary(FakeReasoningProvider):
            async def solve(self, request):  # type: ignore[override]
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise RetryableError("transient", reason_code=ReasonCode.LLM_TIMEOUT)
                return await original_solve(self, request)

        primary = OnceFailPrimary(default_answer="A")
        fallback = FakeReasoningProvider(default_answer="B")
        result, provider = await solve_question(
            1, "Q", _ALTS, [], primary=primary, fallback=fallback, max_retries=2
        )
        assert provider == "anthropic"
        assert call_count == 2
