from __future__ import annotations

import hashlib
import struct

import pytest

from src.pages_to_audio.rgb.canonical import (
    build_payload,
    canonical_items_bytes,
    payload_sha256,
    validate_payload_sha256,
)
from src.pages_to_audio.rgb.policy import DEFAULT_PALETTE
from src.pages_to_audio.rgb.schemas import RgbDefaults, RgbOverride


def _build(answers: str):
    payload, raw = build_payload(
        session_id="S-1",
        sequence_id="rgb-1",
        revision=1,
        answers=answers,
        defaults=RgbDefaults(brightness_percent=12, on_ms=3000, off_ms=5000),
        palette={key: value.model_copy(deep=True) for key, value in DEFAULT_PALETTE.items()},
    )
    return payload, raw


def test_single_item_matches_firmware_golden_vector() -> None:
    payload, _ = _build("A")
    expected = struct.pack("<BBBBBII", ord("A"), 255, 255, 255, 12, 3000, 5000)
    assert canonical_items_bytes(payload) == expected
    assert payload.sha256 == "8a2b2c9188f7e8be635244c53d5b4aad52c595407ef35f7e96b2471a310ad893"
    assert payload_sha256(payload) == payload.sha256


def test_five_item_matches_firmware_golden_vector() -> None:
    payload, _ = _build("ABCDE")
    assert len(canonical_items_bytes(payload)) == 65
    assert payload.sha256 == "6f2f655b4ea2ee02ee009a938cc95515f6ff38309b3b2ddcb0594057a5151f17"


def test_override_changes_only_resolved_item() -> None:
    payload, _ = build_payload(
        session_id="S-1",
        sequence_id="rgb-1",
        revision=1,
        answers="AB",
        defaults=RgbDefaults(),
        palette={key: value.model_copy(deep=True) for key, value in DEFAULT_PALETTE.items()},
        overrides=[RgbOverride(index=1, rgb=(1, 2, 3), brightness_percent=50)],
    )
    assert canonical_items_bytes(payload)[13:18] == bytes((ord("B"), 1, 2, 3, 50))
    validate_payload_sha256(payload)


def test_hash_mismatch_is_rejected() -> None:
    payload, _ = _build("A")
    invalid = payload.model_copy(update={"sha256": hashlib.sha256(b"wrong").hexdigest()})
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_payload_sha256(invalid)
