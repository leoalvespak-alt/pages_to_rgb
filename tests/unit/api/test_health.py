"""Unit tests for health endpoints — no external I/O."""

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    app = create_app()
    return TestClient(app)


def test_liveness_200(client: TestClient) -> None:
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readiness_200(client: TestClient) -> None:
    r = client.get("/api/v1/health/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_dependencies_shape(client: TestClient) -> None:
    r = client.get("/api/v1/health/dependencies")
    assert r.status_code == 200
    data = r.json()
    assert "dependencies" in data
    deps = data["dependencies"]
    assert "database" in deps
    assert "supabase_storage" in deps
    assert "temporal" in deps
    for dep in deps.values():
        assert "status" in dep
        assert "checked_at" in dep


def test_app_imports_without_side_effect() -> None:
    from apps.api.main import create_app as _create  # noqa: F401
