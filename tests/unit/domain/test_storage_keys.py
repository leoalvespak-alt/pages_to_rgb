"""Tests for storage key conventions — §12.2."""

import pytest

from src.pages_to_audio.storage.keys import (
    audio_final_key,
    audio_status_key,
    derived_key,
    frame_key,
    ocr_raw_key,
    page_original_key,
)


@pytest.mark.unit
def test_frame_key() -> None:
    k = frame_key("session-1", "capture-abc", 5)
    assert k == "sessions/session-1/frames/capture-abc/5.jpg"


@pytest.mark.unit
def test_page_original_key() -> None:
    k = page_original_key("session-1", 3)
    assert k == "sessions/session-1/pages/3/original.jpg"


@pytest.mark.unit
def test_derived_key() -> None:
    k = derived_key("session-1", "deskew", "artifact-uuid")
    assert k == "sessions/session-1/derived/deskew/artifact-uuid.jpg"


@pytest.mark.unit
def test_ocr_raw_key() -> None:
    k = ocr_raw_key("session-1", "google", 2)
    assert k == "sessions/session-1/ocr/google/2.json"


@pytest.mark.unit
def test_audio_status_key() -> None:
    k = audio_status_key("session-1", "status-uuid")
    assert k == "sessions/session-1/audio/status/status-uuid.mp3"


@pytest.mark.unit
def test_audio_final_key() -> None:
    k = audio_final_key("session-1", "final-uuid")
    assert k == "sessions/session-1/audio/final/final-uuid.mp3"
