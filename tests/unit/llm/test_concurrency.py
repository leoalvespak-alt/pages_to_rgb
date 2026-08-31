"""Tests for LLM concurrency control — §32, §8.6."""

from __future__ import annotations

import asyncio

import pytest

from src.pages_to_audio.llm.concurrency import get_semaphore, reset_semaphores


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_semaphores()


class TestGetSemaphore:
    def test_returns_semaphore(self) -> None:
        sem = get_semaphore("anthropic")
        assert isinstance(sem, asyncio.Semaphore)

    def test_same_provider_returns_same_semaphore(self) -> None:
        s1 = get_semaphore("anthropic")
        s2 = get_semaphore("anthropic")
        assert s1 is s2

    def test_different_providers_different_semaphores(self) -> None:
        s1 = get_semaphore("anthropic")
        s2 = get_semaphore("deepseek")
        assert s1 is not s2

    @pytest.mark.asyncio
    async def test_concurrency_limit_is_respected(self) -> None:
        """§8.6.2: prove that at most MAX_LLM_CONCURRENCY tasks run simultaneously."""
        from src.pages_to_audio.config.settings import get_settings

        limit = get_settings().MAX_LLM_CONCURRENCY
        sem = get_semaphore("anthropic_test")

        concurrent_count = 0
        max_observed = 0

        async def task() -> None:
            nonlocal concurrent_count, max_observed
            async with sem:
                concurrent_count += 1
                max_observed = max(max_observed, concurrent_count)
                await asyncio.sleep(0)
                concurrent_count -= 1

        await asyncio.gather(*[task() for _ in range(limit * 3)])
        assert max_observed <= limit

    def test_reset_clears_semaphores(self) -> None:
        s1 = get_semaphore("anthropic")
        reset_semaphores()
        s2 = get_semaphore("anthropic")
        assert s1 is not s2
