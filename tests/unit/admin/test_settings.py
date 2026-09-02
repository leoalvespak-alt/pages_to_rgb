from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from pydantic import ValidationError

from apps.api.routers.admin_settings import _probe_provider
from apps.api.schemas.admin import AdminSettingsUpdate, PaletteColor
from src.pages_to_audio.admin.settings_service import (
    SettingsCryptoError,
    decrypt_secret,
    encrypt_secret,
    rgb_for_answer,
    update_admin_settings,
)
from src.pages_to_audio.config.settings import AppSettings, reset_settings_cache
from src.pages_to_audio.db.models.admin_settings import AdminSettings


def test_admin_secret_encryption_round_trip_and_tamper() -> None:
    settings = AppSettings(APP_ENV="test", ADMIN_SETTINGS_ENCRYPTION_KEY="unit-test-key")
    encrypted = encrypt_secret("sk-private", settings)
    assert encrypted != "sk-private"
    assert decrypt_secret(encrypted, settings) == "sk-private"
    with pytest.raises(SettingsCryptoError):
        decrypt_secret(encrypted[:-2] + "xx", settings)


def test_palette_requires_exact_letters_and_valid_channels() -> None:
    with pytest.raises(ValidationError):
        AdminSettingsUpdate(version=1, palette={"A": PaletteColor(rgb=(0, 0, 0))})
    with pytest.raises(ValidationError):
        PaletteColor(rgb=(256, 0, 0))


def test_snapshot_rgb_wins_and_fallback_is_stable() -> None:
    snapshot = {"palette": {letter: {"rgb": [1, 2, 3]} for letter in "ABCDE"}}
    assert rgb_for_answer(snapshot, "EXAM", "A") == [1, 2, 3]
    assert rgb_for_answer(None, "HANDWRITTEN_WORD", "A") == [0, 0, 255]


def test_set_and_clear_key_are_mutually_exclusive() -> None:
    with pytest.raises(ValidationError):
        AdminSettingsUpdate(version=1, deepseek_api_key="sk-new", clear_deepseek_api_key=True)


@pytest.mark.asyncio
async def test_update_palette_version_and_audit(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_SETTINGS_ENCRYPTION_KEY", "update-test-key")
    reset_settings_cache()
    row = AdminSettings(
        singleton_key=1,
        version=3,
        palette={letter: {"rgb": [0, 0, 0]} for letter in "ABCDE"},
        handwritten_palette={letter: {"rgb": [0, 0, 0]} for letter in "ABCDE"},
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=row)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    new_palette = {letter: PaletteColor(rgb=(1, 2, 3)) for letter in "ABCDE"}
    result = await update_admin_settings(
        db,
        AdminSettingsUpdate(
            version=3,
            palette=new_palette,
            deepseek_api_key="sk-secret",
        ),
    )
    assert result.version == 4
    assert result.palette["A"]["rgb"] == [1, 2, 3]
    assert result.deepseek_api_key_encrypted != "sk-secret"
    assert db.add.call_count == 1
    reset_settings_cache()


@pytest.mark.asyncio
async def test_masked_google_document_credential_is_preserved(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_SETTINGS_ENCRYPTION_KEY", "masked-google-key")
    reset_settings_cache()
    encrypted = encrypt_secret("{service-account-json}")
    row = AdminSettings(
        singleton_key=1,
        version=2,
        google_document_ai_credentials_encrypted=encrypted,
    )
    db = MagicMock()
    db.scalar = AsyncMock(return_value=row)
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    result = await update_admin_settings(
        db,
        AdminSettingsUpdate(version=2, google_document_ai_credentials="••••••••"),
    )
    assert result.google_document_ai_credentials_encrypted == encrypted
    assert (
        decrypt_secret(result.google_document_ai_credentials_encrypted) == "{service-account-json}"
    )
    reset_settings_cache()


@pytest.mark.asyncio
@respx.mock
async def test_provider_probe_success_and_unauthorized() -> None:
    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.1-pro-preview:generateContent"
    ).mock(return_value=httpx.Response(200, json={"candidates": []}))
    await _probe_provider("gemini", "gemini-3.1-pro-preview", "sk-test")
    assert route.called

    route.mock(return_value=httpx.Response(401, json={"error": "invalid"}))
    with pytest.raises(httpx.HTTPStatusError):
        await _probe_provider("gemini", "gemini-3.1-pro-preview", "sk-test")
