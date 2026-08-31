"""Session state machine — the ONLY path for session.status changes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from src.pages_to_audio.common.errors import InvalidStateTransition, ReasonCode
from src.pages_to_audio.domain.enums.audit import AuditEventType, AuditSeverity, AuditStage
from src.pages_to_audio.domain.enums.roles import ActorType
from src.pages_to_audio.domain.enums.session_state import SessionState

if TYPE_CHECKING:
    from src.pages_to_audio.db.models.session import Session
    from src.pages_to_audio.db.uow import UnitOfWork

# Normative allowed-transitions map (§9 + §58)
ALLOWED_TRANSITIONS: dict[SessionState, frozenset[SessionState]] = {
    SessionState.CREATED: frozenset(
        {
            SessionState.CAPTURING,
            SessionState.CANCELLED,
        }
    ),
    SessionState.CAPTURING: frozenset(
        {
            SessionState.CAPTURE_END_CANDIDATE,
            SessionState.CANCELLED,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.CAPTURE_END_CANDIDATE: frozenset(
        {
            SessionState.CAPTURING,
            SessionState.CAPTURE_LOCKING,
            SessionState.CANCELLED,
        }
    ),
    SessionState.CAPTURE_LOCKING: frozenset(
        {
            SessionState.LOCKED,
            SessionState.FAILED_RECOVERABLE,
            SessionState.CANCELLED,
        }
    ),
    SessionState.LOCKED: frozenset(
        {
            SessionState.IMAGE_PROCESSING,
            SessionState.CANCELLED,
        }
    ),
    SessionState.IMAGE_PROCESSING: frozenset(
        {
            SessionState.OCR_PROCESSING,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.OCR_PROCESSING: frozenset(
        {
            SessionState.RECONSTRUCTING,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.RECONSTRUCTING: frozenset(
        {
            SessionState.RESCUE_PROCESSING,
            SessionState.GATE_1,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.RESCUE_PROCESSING: frozenset(
        {
            SessionState.GATE_1,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.GATE_1: frozenset(
        {
            SessionState.BLOCKED_GATE_1,
            SessionState.RAG_RETRIEVING,
        }
    ),
    SessionState.BLOCKED_GATE_1: frozenset(
        {
            SessionState.STATUS_AUDIO,
            SessionState.FAILED_FATAL,
        }
    ),
    SessionState.RAG_RETRIEVING: frozenset(
        {
            SessionState.SOLVING,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.SOLVING: frozenset(
        {
            SessionState.VERIFYING,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.VERIFYING: frozenset(
        {
            SessionState.ARBITRATING,
            SessionState.GATE_2,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.ARBITRATING: frozenset(
        {
            SessionState.GATE_2,
            SessionState.RESCUE_PROCESSING,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.GATE_2: frozenset(
        {
            SessionState.BLOCKED_GATE_2,
            SessionState.STATUS_AUDIO,
            SessionState.TTS_GENERATING,
        }
    ),
    SessionState.BLOCKED_GATE_2: frozenset(
        {
            SessionState.STATUS_AUDIO,
            SessionState.FAILED_FATAL,
        }
    ),
    SessionState.STATUS_AUDIO: frozenset(
        {
            SessionState.TTS_GENERATING,
            SessionState.COMPLETED,
            SessionState.FAILED_FATAL,
        }
    ),
    SessionState.TTS_GENERATING: frozenset(
        {
            SessionState.AUDIO_ASSEMBLING,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.AUDIO_ASSEMBLING: frozenset(
        {
            SessionState.AUDIO_VALIDATING,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.AUDIO_VALIDATING: frozenset(
        {
            SessionState.READY,
            SessionState.FAILED_RECOVERABLE,
        }
    ),
    SessionState.READY: frozenset(
        {
            SessionState.COMPLETED,
        }
    ),
    SessionState.FAILED_RECOVERABLE: frozenset(
        {
            SessionState.IMAGE_PROCESSING,
            SessionState.OCR_PROCESSING,
            SessionState.RECONSTRUCTING,
            SessionState.RESCUE_PROCESSING,
            SessionState.RAG_RETRIEVING,
            SessionState.SOLVING,
            SessionState.VERIFYING,
            SessionState.ARBITRATING,
            # TTS_GENERATING intentionally absent: TTS retries are handled by Temporal
            # activity retries; after exhaustion, workflow transitions to FAILED_FATAL.
            # Invariant 6: TTS_GENERATING is only reachable from GATE_2 / STATUS_AUDIO.
            SessionState.AUDIO_ASSEMBLING,
            SessionState.AUDIO_VALIDATING,
            SessionState.FAILED_FATAL,
            SessionState.CANCELLED,
        }
    ),
    # Terminals — no outgoing transitions
    SessionState.COMPLETED: frozenset(),
    SessionState.FAILED_FATAL: frozenset(),
    SessionState.CANCELLED: frozenset(),
}


async def transition_session(
    uow: UnitOfWork,
    session: Session,
    target_state: SessionState,
    *,
    reason: ReasonCode | None,
    actor: ActorType,
    payload: dict | None = None,
) -> Session:
    """
    The single authorised path for changing session.status.

    Order: validate → update state → generate AuditEvent → persist (atomic).
    Uses pessimistic lock (SELECT FOR UPDATE) to prevent race conditions.
    """
    from src.pages_to_audio.db.models.audit_event import AuditEvent

    current = SessionState(session.status)
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())

    if target_state not in allowed:
        # Record invalid-transition audit event before raising
        invalid_event = AuditEvent(
            session_id=session.id,
            event_type=AuditEventType.INVALID_TRANSITION,
            stage=AuditStage.SYSTEM,
            severity=AuditSeverity.ERROR,
            reason_code=ReasonCode.INVALID_STATE_TRANSITION,
            actor_type=actor,
            payload={
                "from_state": current,
                "to_state": target_state,
                "reason": reason,
            },
        )
        uow.session.add(invalid_event)
        await uow.session.flush()
        raise InvalidStateTransition(current, target_state)

    # Acquire pessimistic lock on the session row
    from sqlalchemy.orm import with_for_update as _wfu

    locked_session = await uow.session.get(type(session), session.id, options=[_wfu()])
    if locked_session is None:
        raise ValueError(f"Session {session.id} not found for locking")

    # Apply state change
    locked_session.status = target_state  # ONLY this function writes status
    locked_session.updated_at = datetime.now(UTC)

    # Generate audit event (in same transaction)
    audit_event = AuditEvent(
        session_id=locked_session.id,
        event_type=AuditEventType.STATE_TRANSITION,
        stage=AuditStage.SYSTEM,
        severity=AuditSeverity.INFO,
        reason_code=reason,
        actor_type=actor,
        payload={
            "from_state": current,
            "to_state": target_state,
            **(payload or {}),
        },
    )
    uow.session.add(audit_event)

    await uow.session.flush()
    return locked_session
