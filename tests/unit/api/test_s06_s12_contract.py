"""S06-S12 - testes de contrato das correcoes (regra 12)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app


def test_knowledge_routes_require_admin_session() -> None:
    # S06.1/A08: sem sessão admin, leitura e escrita são 401.
    client = TestClient(create_app())
    assert client.get("/api/v1/knowledge/documents").status_code == 401
    assert client.get("/api/v1/knowledge/documents/abc").status_code == 401
    assert (
        client.post(
            "/api/v1/knowledge/search-test",
            json={"query": "teste", "top_k": 5},
        ).status_code
        == 401
    )


def test_provider_test_accepts_proposed_config() -> None:
    # S06.6: verificação aceita a proposta do formulário.
    from apps.api.schemas.admin import ProviderTestRequest

    req = ProviderTestRequest(
        provider="google_document_ai",
        model="OCR_PROCESSOR",
        google_document_ai_project_id="proj-x",
        google_document_ai_location="us",
        google_document_ai_processor_id="proc-y",
        google_document_ai_credentials='{"type": "service_account"}',
    )
    assert req.google_document_ai_project_id == "proj-x"
    minimal = ProviderTestRequest(provider="gemini", model="gemini-3.1-pro-preview")
    assert minimal.api_key is None


def test_low_power_profile_constants() -> None:
    from src.pages_to_audio.rgb.policy import (
        LOW_POWER_OFF_MS,
        LOW_POWER_ON_MS,
        RGB_PROFILE_LOW_POWER,
    )

    assert (12, LOW_POWER_ON_MS, LOW_POWER_OFF_MS) == (12, 150, 2850)
    assert RGB_PROFILE_LOW_POWER == "low-power"


def test_gateway_start_stamps_low_power_snapshot() -> None:
    import inspect

    import apps.api.routers.gateway as gw

    src = inspect.getsource(gw.session_start)
    assert '"rgb_profile": "low-power"' in src
    assert '"on_ms": 150' in src
    assert '"off_ms": 2850' in src


def test_orphan_key_parser() -> None:
    from src.pages_to_audio.capture.orphans import parse_frame_key

    assert parse_frame_key("sessions/S1/frames/CAP1/3.jpg") == ("S1", "CAP1", 3)
    assert parse_frame_key("sessions/S1/pages/x.jpg") is None
    assert parse_frame_key("lixo") is None


def test_vector_sql_uses_typed_cast() -> None:
    import inspect

    import src.pages_to_audio.rag.retrieval as retrieval_mod

    src = inspect.getsource(retrieval_mod)
    assert "CAST(:embedding AS vector)" in src
    # Nenhum SQL ativo usa o placeholder ambíguo (menções em comentário ok).
    assert "1 - (kc.embedding <=> :embedding::vector)" not in src
    assert "ORDER BY kc.embedding <=> :embedding::vector" not in src


def test_fts_uses_safe_tsquery_with_savepoint() -> None:
    import inspect

    import src.pages_to_audio.rag.retrieval as retrieval_mod

    src = inspect.getsource(retrieval_mod)
    assert "websearch_to_tsquery" in src
    assert "begin_nested" in src


def test_retrieve_for_session_exists() -> None:
    from src.pages_to_audio.rag.retrieval import retrieve_for_session

    assert callable(retrieve_for_session)


def test_worker_health_endpoint_registered() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/health/worker" in paths
    assert "/api/v1/health/ready" in paths
    assert "/api/v1/health/dependencies" in paths


def test_admin_detail_supports_pagination_params() -> None:
    paths = create_app().openapi()["paths"]
    params = paths["/api/v1/admin/sessions/{public_id}"]["get"]["parameters"]
    names = {p["name"] for p in params}
    assert {"frames_page", "frames_limit", "logs_page", "logs_limit"} <= names


def test_gateway_ack_endpoints_registered() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/gateway/session/{session_id}/command/ack" in paths
    assert "/api/v1/handwritten/session/{session_id}/command/ack" in paths


def test_reindex_response_shape() -> None:
    from apps.api.routers.knowledge import ReindexResponse

    r = ReindexResponse(status="completed", doc_id="d", chunks_reindexed=3, chunks_failed=0)
    assert r.chunks_reindexed == 3


def test_google_credentials_loader_accepts_json_and_path(tmp_path) -> None:  # type: ignore[no-untyped-def]
    import json

    from src.pages_to_audio.ocr.credentials import load_google_credentials

    info = {"type": "service_account", "project_id": "p"}
    creds = load_google_credentials(json.dumps(info))
    assert creds.info is not None and creds.file_path is None
    f = tmp_path / "creds.json"
    f.write_text(json.dumps(info))
    creds2 = load_google_credentials(None, file_fallback=str(f))
    assert creds2.file_path is not None
    with pytest.raises(RuntimeError):
        load_google_credentials('{"type": "other"}')
    with pytest.raises(RuntimeError):
        load_google_credentials(None, file_fallback="/nao/existe.json")
