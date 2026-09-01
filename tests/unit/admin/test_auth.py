from __future__ import annotations

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from apps.api.main import create_app
from src.pages_to_audio.auth.admin import reset_admin_rate_limits
from src.pages_to_audio.config.settings import reset_settings_cache


def _client(monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", PasswordHasher().hash("correct horse"))
    monkeypatch.setenv("SESSION_SECRET", "session-secret-for-tests")
    monkeypatch.setenv("CSRF_SECRET", "csrf-secret-for-tests")
    monkeypatch.setenv("ADMIN_SETTINGS_ENCRYPTION_KEY", "encryption-key-for-tests")
    reset_settings_cache()
    reset_admin_rate_limits()
    return TestClient(create_app())


def test_admin_login_me_logout_and_csrf(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _client(monkeypatch)
    assert client.get("/api/v1/admin/me").status_code == 401
    assert client.post("/api/v1/admin/login", json={"password": "wrong"}).status_code == 401

    login = client.post("/api/v1/admin/login", json={"password": "correct horse"})
    assert login.status_code == 200
    assert "HttpOnly" in login.headers["set-cookie"]
    assert "admin_session" not in login.json()

    me = client.get("/api/v1/admin/me")
    assert me.status_code == 200
    csrf = me.json()["csrf_token"]
    assert client.post("/api/v1/admin/logout").status_code == 403
    assert client.post("/api/v1/admin/logout", headers={"X-CSRF-Token": csrf}).status_code == 204
    assert client.get("/api/v1/admin/me").status_code == 401
    reset_settings_cache()


def test_admin_cookie_tampering_is_rejected(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _client(monkeypatch)
    client.cookies.set("admin_session", "not-a-jwt")
    assert client.get("/api/v1/admin/me").status_code == 401
    reset_settings_cache()


def test_admin_openapi_contracts_are_exposed() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/admin/login" in paths
    assert "/api/v1/admin/me" in paths
    assert "/api/v1/admin/logout" in paths
    assert "/api/v1/admin/settings" in paths
    assert "/api/v1/admin/settings/test" in paths
