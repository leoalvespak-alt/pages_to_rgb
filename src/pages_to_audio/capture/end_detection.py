"""Redundant capture termination — §16. Five conditions in priority order."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from src.pages_to_audio.domain.enums.end_reason import EndReason
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


@dataclass
class CaptureState:
    logical_pages_count: int
    expected_pages: int
    last_activity_at: datetime
    pending_uploads: int = 0
    burst_in_progress: bool = False
    # For open-hand detection
    open_hand_confidence: float = 0.0
    exam_document_present: bool = True
    open_hand_confirmations: int = 0
    open_hand_window_seconds: float = 0.0


def evaluate_end_conditions(
    state: CaptureState,
    *,
    manual_requested: bool = False,
    visual_marker_detected: bool = False,
    soft_idle_seconds: int = 30,
    hard_idle_seconds: int = 120,
    open_hand_threshold: float = 0.85,
    open_hand_min_confirmations: int = 2,
    open_hand_max_window_seconds: float = 5.0,
) -> EndReason | None:
    """
    Evaluate end conditions in priority order (§16).
    Returns the EndReason if capture should end, None if capture should continue.
    """
    now = datetime.now(UTC)
    idle_seconds = (now - state.last_activity_at).total_seconds()

    # 1. Expected pages reached
    if state.logical_pages_count >= state.expected_pages:
        logger.info("capture_end_expected_pages", pages=state.logical_pages_count)
        return EndReason.EXPECTED_PAGES_REACHED

    # 2. Manual end command
    if manual_requested:
        logger.info("capture_end_manual")
        return EndReason.MANUAL

    # 3. Visual marker detected
    if visual_marker_detected:
        logger.info("capture_end_visual_marker")
        return EndReason.VISUAL_MARKER

    # 4. Open-hand gesture (all conditions must be met — §16.1)
    if (
        state.open_hand_confidence >= open_hand_threshold
        and not state.exam_document_present
        and state.open_hand_confirmations >= open_hand_min_confirmations
        and state.open_hand_window_seconds <= open_hand_max_window_seconds
    ):
        logger.info("capture_end_open_hand", confirmations=state.open_hand_confirmations)
        return EndReason.OPEN_HAND

    # 5. Hard idle — only when ALL sub-conditions satisfied (§16.2)
    if (
        idle_seconds >= hard_idle_seconds
        and state.pending_uploads == 0
        and not state.burst_in_progress
    ):
        logger.info("capture_end_hard_idle", idle_seconds=idle_seconds)
        return EndReason.HARD_IDLE

    return None


def is_soft_idle(state: CaptureState, *, soft_idle_seconds: int = 30) -> bool:
    """Soft idle — alert only, never terminates capture (§16.2)."""
    now = datetime.now(UTC)
    return (now - state.last_activity_at).total_seconds() >= soft_idle_seconds
