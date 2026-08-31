"""Unit tests for prompt registry — §6.2."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from src.pages_to_audio.llm.prompt_registry import get_prompt, invalidate_cache


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    invalidate_cache()


def test_reconstruction_prompt_loads() -> None:
    content, h = get_prompt("reconstruction", "v1")
    assert len(content) > 100
    assert len(h) == 64  # SHA-256 hex


def test_solver_prompt_loads() -> None:
    content, h = get_prompt("solver", "v1")
    assert len(content) > 50
    assert len(h) == 64


def test_verifier_prompt_loads() -> None:
    content, h = get_prompt("verifier", "v1")
    assert len(content) > 50


def test_arbiter_prompt_loads() -> None:
    content, h = get_prompt("arbiter", "v1")
    assert len(content) > 50


def test_hash_matches_file_content() -> None:
    content, h = get_prompt("reconstruction", "v1")
    expected = hashlib.sha256(content.encode()).hexdigest()
    assert h == expected


def test_different_content_different_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Altering a prompt file must produce a different hash."""
    from src.pages_to_audio.llm import prompt_registry as reg

    prompts_root = tmp_path / "prompts" / "reconstruction"
    prompts_root.mkdir(parents=True)
    v1 = prompts_root / "v1.md"
    v2 = prompts_root / "v2.md"
    v1.write_text("Content A", encoding="utf-8")
    v2.write_text("Content B", encoding="utf-8")

    monkeypatch.setattr(reg, "_PROMPTS_ROOT", tmp_path / "prompts")
    reg.invalidate_cache()

    _, h1 = reg.get_prompt("reconstruction", "v1")
    _, h2 = reg.get_prompt("reconstruction", "v2")
    assert h1 != h2


def test_missing_prompt_raises() -> None:
    with pytest.raises(FileNotFoundError):
        get_prompt("nonexistent_prompt_xyz", "v99")
