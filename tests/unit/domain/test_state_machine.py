"""Unit tests for the session state machine — no I/O."""

from __future__ import annotations

import pytest

from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.domain.state_machine import ALLOWED_TRANSITIONS

# ---------------------------------------------------------------------------
# Coverage of every permitted transition
# ---------------------------------------------------------------------------

VALID_PAIRS = [
    (SessionState.CREATED, SessionState.CAPTURING),
    (SessionState.CREATED, SessionState.CANCELLED),
    (SessionState.CAPTURING, SessionState.CAPTURE_END_CANDIDATE),
    (SessionState.CAPTURING, SessionState.CANCELLED),
    (SessionState.CAPTURING, SessionState.FAILED_RECOVERABLE),
    (SessionState.CAPTURE_END_CANDIDATE, SessionState.CAPTURING),
    (SessionState.CAPTURE_END_CANDIDATE, SessionState.CAPTURE_LOCKING),
    (SessionState.CAPTURE_END_CANDIDATE, SessionState.CANCELLED),
    (SessionState.CAPTURE_LOCKING, SessionState.LOCKED),
    (SessionState.CAPTURE_LOCKING, SessionState.FAILED_RECOVERABLE),
    (SessionState.CAPTURE_LOCKING, SessionState.CANCELLED),
    (SessionState.LOCKED, SessionState.IMAGE_PROCESSING),
    (SessionState.LOCKED, SessionState.CANCELLED),
    (SessionState.IMAGE_PROCESSING, SessionState.OCR_PROCESSING),
    (SessionState.IMAGE_PROCESSING, SessionState.FAILED_RECOVERABLE),
    (SessionState.OCR_PROCESSING, SessionState.RECONSTRUCTING),
    (SessionState.OCR_PROCESSING, SessionState.FAILED_RECOVERABLE),
    (SessionState.RECONSTRUCTING, SessionState.RESCUE_PROCESSING),
    (SessionState.RECONSTRUCTING, SessionState.GATE_1),
    (SessionState.RECONSTRUCTING, SessionState.FAILED_RECOVERABLE),
    (SessionState.RESCUE_PROCESSING, SessionState.GATE_1),
    (SessionState.RESCUE_PROCESSING, SessionState.FAILED_RECOVERABLE),
    (SessionState.GATE_1, SessionState.BLOCKED_GATE_1),
    (SessionState.GATE_1, SessionState.RAG_RETRIEVING),
    (SessionState.BLOCKED_GATE_1, SessionState.STATUS_AUDIO),
    (SessionState.BLOCKED_GATE_1, SessionState.FAILED_FATAL),
    (SessionState.RAG_RETRIEVING, SessionState.SOLVING),
    (SessionState.RAG_RETRIEVING, SessionState.FAILED_RECOVERABLE),
    (SessionState.SOLVING, SessionState.VERIFYING),
    (SessionState.SOLVING, SessionState.FAILED_RECOVERABLE),
    (SessionState.VERIFYING, SessionState.ARBITRATING),
    (SessionState.VERIFYING, SessionState.GATE_2),
    (SessionState.VERIFYING, SessionState.FAILED_RECOVERABLE),
    (SessionState.ARBITRATING, SessionState.GATE_2),
    (SessionState.ARBITRATING, SessionState.RESCUE_PROCESSING),
    (SessionState.ARBITRATING, SessionState.FAILED_RECOVERABLE),
    (SessionState.GATE_2, SessionState.BLOCKED_GATE_2),
    (SessionState.GATE_2, SessionState.STATUS_AUDIO),
    (SessionState.GATE_2, SessionState.TTS_GENERATING),
    (SessionState.BLOCKED_GATE_2, SessionState.STATUS_AUDIO),
    (SessionState.BLOCKED_GATE_2, SessionState.FAILED_FATAL),
    (SessionState.STATUS_AUDIO, SessionState.TTS_GENERATING),
    (SessionState.STATUS_AUDIO, SessionState.COMPLETED),
    (SessionState.STATUS_AUDIO, SessionState.FAILED_FATAL),
    (SessionState.TTS_GENERATING, SessionState.AUDIO_ASSEMBLING),
    (SessionState.TTS_GENERATING, SessionState.FAILED_RECOVERABLE),
    (SessionState.AUDIO_ASSEMBLING, SessionState.AUDIO_VALIDATING),
    (SessionState.AUDIO_ASSEMBLING, SessionState.FAILED_RECOVERABLE),
    (SessionState.AUDIO_VALIDATING, SessionState.READY),
    (SessionState.AUDIO_VALIDATING, SessionState.FAILED_RECOVERABLE),
    (SessionState.READY, SessionState.COMPLETED),
    (SessionState.FAILED_RECOVERABLE, SessionState.FAILED_FATAL),
    (SessionState.FAILED_RECOVERABLE, SessionState.CANCELLED),
]

INVALID_PAIRS = [
    (SessionState.CREATED, SessionState.LOCKED),
    (SessionState.CREATED, SessionState.COMPLETED),
    (SessionState.LOCKED, SessionState.SOLVING),
    (SessionState.GATE_1, SessionState.SOLVING),  # must go through RAG first
    (SessionState.COMPLETED, SessionState.CAPTURING),
    (SessionState.FAILED_FATAL, SessionState.CAPTURING),
    (SessionState.CANCELLED, SessionState.CAPTURING),
    (SessionState.SOLVING, SessionState.GATE_1),  # no backward skip
]


@pytest.mark.unit
@pytest.mark.parametrize("from_state,to_state", VALID_PAIRS)
def test_valid_transitions_in_map(from_state: SessionState, to_state: SessionState) -> None:
    allowed = ALLOWED_TRANSITIONS.get(from_state, frozenset())
    assert to_state in allowed, f"{from_state} → {to_state} should be allowed"


@pytest.mark.unit
@pytest.mark.parametrize("from_state,to_state", INVALID_PAIRS)
def test_invalid_transitions_not_in_map(from_state: SessionState, to_state: SessionState) -> None:
    allowed = ALLOWED_TRANSITIONS.get(from_state, frozenset())
    assert to_state not in allowed, f"{from_state} → {to_state} should NOT be allowed"


@pytest.mark.unit
def test_all_session_states_covered() -> None:
    """Every SessionState must appear as a key in ALLOWED_TRANSITIONS."""
    for state in SessionState:
        assert state in ALLOWED_TRANSITIONS, f"{state} missing from ALLOWED_TRANSITIONS"


@pytest.mark.unit
def test_terminal_states_have_no_outgoing() -> None:
    terminals = {SessionState.COMPLETED, SessionState.FAILED_FATAL, SessionState.CANCELLED}
    for state in terminals:
        assert not ALLOWED_TRANSITIONS[state], f"Terminal {state} must have no outgoing transitions"


@pytest.mark.unit
def test_solver_unreachable_without_gate_1() -> None:
    """Invariant 5: structural impossibility of solving before Gate 1."""
    # GATE_1 must go to RAG_RETRIEVING, then SOLVING — never SOLVING directly
    gate_1_targets = ALLOWED_TRANSITIONS[SessionState.GATE_1]
    assert SessionState.SOLVING not in gate_1_targets
    # RAG_RETRIEVING → SOLVING is the only path
    assert SessionState.SOLVING in ALLOWED_TRANSITIONS[SessionState.RAG_RETRIEVING]


@pytest.mark.unit
def test_tts_unreachable_without_gate_2() -> None:
    """Invariant 6: structural impossibility of TTS before Gate 2."""
    # GATE_2 is the only source that reaches TTS_GENERATING
    for state, targets in ALLOWED_TRANSITIONS.items():
        if state != SessionState.GATE_2 and state != SessionState.STATUS_AUDIO:
            assert SessionState.TTS_GENERATING not in targets, (
                f"TTS_GENERATING should only be reachable from GATE_2/STATUS_AUDIO, not {state}"
            )
