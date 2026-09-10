from __future__ import annotations

from src.pages_to_audio.capture.commands import _desired_command
from src.pages_to_audio.domain.enums.session_state import SessionState


def test_esp32_commands_use_the_v2_camera_profile() -> None:
    command, payload = _desired_command(
        SessionState.CAPTURING,
        phase=None,
        capture_source="ESP32_CAMERA",
        camera_config={
            "frame_count": 2,
            "intra_frame_gap_ms": 220,
            "frame_size": "UXGA",
            "esp_jpeg_quality": 10,
        },
    )

    assert command == "CAPTURE_FULL"
    assert payload == {
        "frames": 2,
        "gap_ms": 220,
        "frame_size": "UXGA",
        "jpeg_quality": 10,
    }


def test_esp32_probe_is_still_image_only_and_uses_production_limits() -> None:
    command, payload = _desired_command(
        SessionState.CAPTURING,
        phase="PROBE",
        capture_source="ESP32_CAMERA",
    )

    assert command == "CAPTURE_PROBE"
    assert payload == {
        "frames": 1,
        "gap_ms": 0,
        "frame_size": "UXGA",
        "jpeg_quality": 10,
    }
