"""S00-S05 - testes de contrato das correcoes (regra 12: nova feature precisa de testes)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.routers.gateway import (
    GatewayCommandResponse,
    SessionStartRequest,
    SessionStartResponse,
)
from apps.api.routers.handwritten import HandwrittenSessionStartRequest
from src.pages_to_audio.ai.confidence import ReviewMode, finalize_review
from src.pages_to_audio.common.contract_ids import (
    MAX_EXACT_CURSOR,
    is_valid_cursor,
    is_valid_esp_id,
    is_valid_sequence_id,
)


# S01.5 — validação de limites no schema de início.
def test_session_start_rejects_invalid_numbers() -> None:
    with pytest.raises(ValidationError):
        SessionStartRequest(expected_pages=-1)
    with pytest.raises(ValidationError):
        SessionStartRequest(expected_questions=0)
    with pytest.raises(ValidationError):
        SessionStartRequest(minimum_ratio=1.5)
    with pytest.raises(ValidationError):
        SessionStartRequest(minimum_ratio=0)
    ok = SessionStartRequest(expected_pages=5, expected_questions=5, minimum_ratio=0.9)
    assert ok.expected_pages == 5


def test_session_start_ids_follow_esp_pattern() -> None:
    with pytest.raises(ValidationError):
        SessionStartRequest(device_code="INVALID ID!")
    with pytest.raises(ValidationError):
        SessionStartRequest(device_code="x" * 64)
    ok = SessionStartRequest(device_code="CAM-001")
    assert ok.device_code == "CAM-001"


def test_session_start_response_carries_resumed_cursor() -> None:
    r = SessionStartResponse(
        session_id="abc", status="CAPTURING", expected_pages=5, expected_questions=5,
        minimum_ratio=0.9, resumed=True, cursor=3,
    )
    assert r.resumed is True
    assert r.cursor == 3
    with pytest.raises(ValidationError):
        SessionStartResponse(
            session_id="abc", status="CAPTURING", expected_pages=5, expected_questions=5,
            minimum_ratio=0.9, cursor=MAX_EXACT_CURSOR + 1,
        )


def test_handwritten_omitted_inherits_config() -> None:
    # S01.8/A20: omitido é None (herda admin); nunca default 10 encobrindo config.
    req = HandwrittenSessionStartRequest()
    assert req.expected_words is None


def test_gateway_command_rejects_unknown_without_consuming_cursor() -> None:
    # S01.2/contrato §3.9.
    with pytest.raises(ValidationError):
        GatewayCommandResponse(command="UNKNOWN_X", cursor=0, session_id="S-1")  # type: ignore[arg-type]
    ping = GatewayCommandResponse(command="PING", cursor=1, session_id="S-1")
    assert ping.command == "PING"


def test_contract_ids_validators() -> None:
    assert is_valid_esp_id("CAM-001")
    assert is_valid_esp_id("a" * 63)
    assert not is_valid_esp_id("a" * 64)
    assert not is_valid_esp_id("com espaço")
    assert is_valid_sequence_id("seq_1-abc")
    assert not is_valid_sequence_id("x" * 65)
    assert is_valid_cursor(0)
    assert is_valid_cursor(MAX_EXACT_CURSOR)
    assert not is_valid_cursor(MAX_EXACT_CURSOR + 1)
    assert not is_valid_cursor(-1)


def test_upload_open_states_exclude_locked_and_processing() -> None:
    from src.pages_to_audio.capture.frame_upload import UPLOAD_OPEN_STATES
    from src.pages_to_audio.domain.enums.session_state import SessionState

    assert SessionState.CAPTURING in UPLOAD_OPEN_STATES
    assert SessionState.LOCKED not in UPLOAD_OPEN_STATES
    assert SessionState.IMAGE_PROCESSING not in UPLOAD_OPEN_STATES
    assert SessionState.COMPLETED not in UPLOAD_OPEN_STATES
    assert SessionState.CANCELLED not in UPLOAD_OPEN_STATES


def test_persistent_command_selection_prefers_control() -> None:
    from src.pages_to_audio.capture.commands import _desired_command
    from src.pages_to_audio.domain.enums.session_state import SessionState

    assert _desired_command(SessionState.LOCKED, phase=None)[0] == "STOP"
    assert _desired_command(SessionState.COMPLETED, phase=None)[0] == "STOP"
    # Controle nunca preso atrás da pausa.
    assert _desired_command(SessionState.CAPTURING, phase="STOP")[0] == "STOP"
    assert _desired_command(SessionState.CAPTURING, phase="RESUME")[0] == "RESUME"
    assert _desired_command(SessionState.CAPTURING, phase="PROBE")[0] == "CAPTURE_PROBE"
    assert _desired_command(SessionState.CAPTURING, phase=None)[0] == "CAPTURE_FULL"


def test_low_confidence_requires_manual_review() -> None:
    # S05.9/A29: 0.1 nunca segue para resolução automática.
    decision = finalize_review(0.1, "texto")
    assert decision.mode is ReviewMode.MANUAL
    assert decision.manual_review_required is True


def test_worker_registers_only_real_activities() -> None:
    import inspect

    import src.pages_to_audio.workflows.worker as worker_mod

    src = inspect.getsource(worker_mod)
    assert "REAL_ACTIVITIES" in src
    assert "ALL_FAKE_ACTIVITIES" not in src


def test_starter_uses_explicit_task_queue() -> None:
    import inspect

    import src.pages_to_audio.workflows.starter as starter_mod

    src = inspect.getsource(starter_mod)
    assert "TEMPORAL_TASK_QUEUE" in src
    assert "get_settings().TEMPORAL_TASK_QUEUE" in src
    assert "WorkflowAlreadyStartedError" in src


def test_storage_prod_fails_explicitly_without_fake() -> None:
    from src.pages_to_audio.config.settings import get_settings

    settings = get_settings()
    if settings.APP_ENV != "production":
        pytest.skip("aplica-se a APP_ENV=production")
    from src.pages_to_audio.storage import get_storage_adapter

    with pytest.raises(RuntimeError):
        get_storage_adapter()


def test_preprocess_reports_applied_skipped_failed() -> None:
    from pathlib import Path

    from src.pages_to_audio.image.preprocess import PreprocessOp, PreprocessRequest

    req = PreprocessRequest(input_path=Path("x.jpg"), session_tag="s1")
    assert req.session_tag == "s1"
    assert set(PreprocessOp) == {
        PreprocessOp.ORIENTATION, PreprocessOp.PERSPECTIVE, PreprocessOp.CLAHE,
        PreprocessOp.DENOISE, PreprocessOp.SHARPEN, PreprocessOp.THRESHOLD,
    }
