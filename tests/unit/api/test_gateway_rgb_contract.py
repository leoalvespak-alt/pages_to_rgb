from __future__ import annotations

import pytest
from pydantic import ValidationError

from apps.api.main import create_app
from apps.api.routers.gateway_rgb import ResultPollResponse, RgbSequenceEventRequest
from src.pages_to_audio.rgb.schemas import RgbEventName, RgbResultCommand


def test_rgb_routes_are_exposed_in_openapi() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/gateway/session/{session_id}/result" in paths
    assert "/api/v1/gateway/session/{session_id}/rgb-sequence" in paths
    assert "/api/v1/gateway/session/{session_id}/rgb-sequence/event" in paths


def test_ready_command_shape_matches_firmware_parser() -> None:
    response = ResultPollResponse(
        command=RgbResultCommand.RGB_SEQUENCE_READY,
        cursor=14,
        session_id="S-1",
        sequence_id="rgb-0123456789abcdef0123456789abcdef",
        revision=1,
        item_count=70,
        sha256="a" * 64,
    )
    assert response.model_dump(mode="json")["command"] == "RGB_SEQUENCE_READY"
    assert response.model_dump(mode="json")["item_count"] == 70


def test_event_schema_rejects_extra_fields_and_bad_ranges() -> None:
    parsed = RgbSequenceEventRequest(
        device_id="CAM-001",
        session_id="S-1",
        sequence_id="rgb-1",
        revision=1,
        event="COMPLETED",
        next_index=1,
        item_count=1,
    )
    assert parsed.event is RgbEventName.COMPLETED

    with pytest.raises(ValidationError):
        RgbSequenceEventRequest(
            device_id="CAM-001",
            session_id="S-1",
            sequence_id="rgb-1",
            revision=1,
            event=RgbEventName.COMPLETED,
            next_index=101,
            item_count=100,
            unexpected="not-allowed",
        )
