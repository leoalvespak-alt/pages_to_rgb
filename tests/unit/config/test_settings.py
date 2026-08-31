"""Unit tests for settings — no I/O, no network."""

import pytest

from src.pages_to_audio.config.settings import AppSettings, reset_settings_cache


@pytest.fixture(autouse=True)
def _reset_cache() -> None:
    reset_settings_cache()


def test_loads_development_without_error() -> None:
    settings = AppSettings(APP_ENV="development")
    assert settings.APP_ENV == "development"


def test_default_capture_values() -> None:
    settings = AppSettings(APP_ENV="development")
    assert settings.capture_defaults.EXPECTED_PAGES == 30
    assert settings.capture_defaults.EXPECTED_QUESTIONS == 70
    assert settings.capture_defaults.MINIMUM_RATIO == 0.90


def test_minimum_ratio_validation() -> None:
    with pytest.raises(Exception):
        AppSettings(APP_ENV="development", **{"DEFAULT_MINIMUM_RATIO": "0.0"})

    with pytest.raises(Exception):
        AppSettings(APP_ENV="development", **{"DEFAULT_MINIMUM_RATIO": "1.1"})


def test_production_fails_without_secrets() -> None:
    with pytest.raises(Exception, match="Production requires"):
        AppSettings(APP_ENV="production")


def test_repr_does_not_leak_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "super-secret-value")
    settings = AppSettings(APP_ENV="development")
    r = repr(settings)
    assert "super-secret-value" not in r


def test_model_dump_redacts_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SESSION_SECRET", "my-session-secret")
    settings = AppSettings(APP_ENV="development")
    dumped = settings.model_dump()
    import json

    serialized = json.dumps(dumped)
    assert "my-session-secret" not in serialized
