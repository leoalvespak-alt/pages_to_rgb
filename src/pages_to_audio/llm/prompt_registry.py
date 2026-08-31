"""Versioned prompt registry — §6.2.

Prompts live in files (never hardcoded in Python).
SHA-256 of the file content = prompt version hash, registered with every use.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_PROMPTS_ROOT = Path(__file__).parent.parent.parent.parent / "prompts"


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


@lru_cache(maxsize=64)
def _load_prompt(path: Path) -> tuple[str, str]:
    """Return (content, sha256_hash). Cached after first read."""
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    content = path.read_text(encoding="utf-8")
    h = _sha256(content)
    logger.debug("prompt_loaded", path=str(path), hash=h[:12])
    return content, h


def get_prompt(name: str, version: str = "v1") -> tuple[str, str]:
    """
    Load a prompt by name and version.

    Args:
        name: prompt directory name (e.g., "reconstruction", "solver")
        version: version string (e.g., "v1")

    Returns:
        (content, sha256_hash)
    """
    path = _PROMPTS_ROOT / name / f"{version}.md"
    return _load_prompt(path)


def invalidate_cache() -> None:
    """Clear the prompt cache — use in tests only."""
    _load_prompt.cache_clear()
