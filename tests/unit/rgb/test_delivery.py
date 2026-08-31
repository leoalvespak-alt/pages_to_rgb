from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

import pytest

from src.pages_to_audio.db.models.rgb_sequence import RgbSequence
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.rgb.canonical import build_payload
from src.pages_to_audio.rgb.delivery import derive_command, sequence_payload
from src.pages_to_audio.rgb.policy import DEFAULT_PALETTE
from src.pages_to_audio.rgb.schemas import RgbDefaults, RgbResultCommand


@pytest.mark.parametrize(
    ("state", "processing_started", "expected"),
    [
        (SessionState.CREATED, None, RgbResultCommand.RESULT_NOT_STARTED),
        (SessionState.IMAGE_PROCESSING, None, RgbResultCommand.RESULT_PROCESSING),
        (SessionState.BLOCKED_GATE_2, None, RgbResultCommand.RESULT_CANCELLED),
        (SessionState.READY, None, RgbResultCommand.RESULT_CANCELLED),
    ],
)
def test_derive_command_maps_session_lifecycle(
    state: SessionState,
    processing_started: object,
    expected: RgbResultCommand,
) -> None:
    session = cast(
        Session,
        SimpleNamespace(status=state.value, processing_started_at=processing_started),
    )

    assert derive_command(session) is expected


def test_started_capture_is_processing_even_before_gate_progress() -> None:
    session = cast(
        Session,
        SimpleNamespace(
            status=SessionState.CAPTURING.value,
            processing_started_at=SimpleNamespace(),
        ),
    )

    assert derive_command(session) is RgbResultCommand.RESULT_PROCESSING


def test_persisted_json_arrays_rehydrate_to_the_same_canonical_payload() -> None:
    payload, _ = build_payload(
        session_id="S-1",
        sequence_id="rgb-1",
        revision=1,
        answers="ABCDE",
        defaults=RgbDefaults(),
        palette={key: value.model_copy(deep=True) for key, value in DEFAULT_PALETTE.items()},
    )
    sequence = RgbSequence(
        id=uuid.uuid4(),
        sequence_id=payload.sequence_id,
        revision=payload.revision,
        schema_version=payload.schema_version,
        status="READY",
        answers=payload.answers,
        item_count=payload.item_count,
        defaults=payload.defaults.model_dump(mode="json"),
        palette={key: value.model_dump(mode="json") for key, value in payload.palette.items()},
        overrides=[],
        payload_sha256=payload.sha256,
        payload_size=65,
    )

    rehydrated, _ = sequence_payload(sequence, session_public_id="S-1")

    assert rehydrated.sha256 == payload.sha256
    assert rehydrated.palette["A"].rgb == (255, 255, 255)
