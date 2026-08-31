"""Per-provider asyncio semaphores for LLM concurrency control — §32.

One semaphore per provider. MAX_LLM_CONCURRENCY defaults to 4 (§8.6.1).
§18: never raise this limit without first measuring resource usage.
§8.6.2: prohibited to fire 70 Solver + 70 Verifier simultaneously.
"""

from __future__ import annotations

import asyncio

from src.pages_to_audio.config.settings import get_settings

_semaphores: dict[str, asyncio.Semaphore] = {}


def get_semaphore(provider: str) -> asyncio.Semaphore:
    """Return (or lazily create) the asyncio.Semaphore for the given provider."""
    if provider not in _semaphores:
        limit = get_settings().MAX_LLM_CONCURRENCY
        _semaphores[provider] = asyncio.Semaphore(limit)
    return _semaphores[provider]


def reset_semaphores() -> None:
    """Discard all semaphores. Call only in tests (asyncio event loop is recreated)."""
    _semaphores.clear()
