"""Tests for the 5 capture end conditions — §16."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.pages_to_audio.capture.end_detection import (
    CaptureState,
    evaluate_end_conditions,
    is_soft_idle,
)
from src.pages_to_audio.domain.enums.end_reason import EndReason


def _state(**kwargs) -> CaptureState:  # type: ignore[return]
    defaults = dict(
        logical_pages_count=0,
        expected_pages=30,
        last_activity_at=datetime.now(UTC),
        pending_uploads=0,
        burst_in_progress=False,
        open_hand_confidence=0.0,
        exam_document_present=True,
        open_hand_confirmations=0,
        open_hand_window_seconds=0.0,
    )
    defaults.update(kwargs)
    return CaptureState(**defaults)


@pytest.mark.unit
def test_expected_pages_reached() -> None:
    state = _state(logical_pages_count=30, expected_pages=30)
    result = evaluate_end_conditions(state)
    assert result == EndReason.EXPECTED_PAGES_REACHED


@pytest.mark.unit
def test_expected_pages_not_reached() -> None:
    state = _state(logical_pages_count=29, expected_pages=30)
    result = evaluate_end_conditions(state)
    assert result is None


@pytest.mark.unit
def test_manual_end() -> None:
    state = _state()
    result = evaluate_end_conditions(state, manual_requested=True)
    assert result == EndReason.MANUAL


@pytest.mark.unit
def test_visual_marker() -> None:
    state = _state()
    result = evaluate_end_conditions(state, visual_marker_detected=True)
    assert result == EndReason.VISUAL_MARKER


@pytest.mark.unit
def test_open_hand_requires_all_conditions() -> None:
    state = _state(
        open_hand_confidence=0.9,
        exam_document_present=False,
        open_hand_confirmations=2,
        open_hand_window_seconds=4.0,
    )
    result = evaluate_end_conditions(state)
    assert result == EndReason.OPEN_HAND


@pytest.mark.unit
def test_single_open_hand_confirmation_does_not_end() -> None:
    """Single confirmation is not enough (§16.1)."""
    state = _state(
        open_hand_confidence=0.9,
        exam_document_present=False,
        open_hand_confirmations=1,
        open_hand_window_seconds=4.0,
    )
    result = evaluate_end_conditions(state)
    assert result is None


@pytest.mark.unit
def test_open_hand_with_document_present_does_not_end() -> None:
    state = _state(
        open_hand_confidence=0.9,
        exam_document_present=True,
        open_hand_confirmations=2,
        open_hand_window_seconds=4.0,
    )
    result = evaluate_end_conditions(state)
    assert result is None


@pytest.mark.unit
def test_soft_idle_does_not_end_capture() -> None:
    """Soft idle is an alert only — never terminates (§16.2)."""
    old = datetime.now(UTC) - timedelta(seconds=40)
    state = _state(last_activity_at=old)
    result = evaluate_end_conditions(state, soft_idle_seconds=30, hard_idle_seconds=120)
    assert result is None
    assert is_soft_idle(state, soft_idle_seconds=30) is True


@pytest.mark.unit
def test_hard_idle_with_pending_uploads_does_not_end() -> None:
    """Hard idle requires no pending uploads (§16.2)."""
    old = datetime.now(UTC) - timedelta(seconds=200)
    state = _state(last_activity_at=old, pending_uploads=1)
    result = evaluate_end_conditions(state, hard_idle_seconds=120)
    assert result is None


@pytest.mark.unit
def test_hard_idle_with_burst_in_progress_does_not_end() -> None:
    old = datetime.now(UTC) - timedelta(seconds=200)
    state = _state(last_activity_at=old, burst_in_progress=True)
    result = evaluate_end_conditions(state, hard_idle_seconds=120)
    assert result is None


@pytest.mark.unit
def test_hard_idle_all_conditions_met() -> None:
    old = datetime.now(UTC) - timedelta(seconds=200)
    state = _state(last_activity_at=old, pending_uploads=0, burst_in_progress=False)
    result = evaluate_end_conditions(state, hard_idle_seconds=120)
    assert result == EndReason.HARD_IDLE


@pytest.mark.unit
def test_priority_expected_pages_over_manual() -> None:
    """Expected pages takes priority over manual (condition 1 > 2)."""
    state = _state(logical_pages_count=30, expected_pages=30)
    result = evaluate_end_conditions(state, manual_requested=True)
    assert result == EndReason.EXPECTED_PAGES_REACHED
