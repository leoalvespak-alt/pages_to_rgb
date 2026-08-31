"""LOCK_SESSION — §3.7. Atomic session locking."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from src.pages_to_audio.common.errors import ReasonCode
from src.pages_to_audio.domain.enums.end_reason import EndReason
from src.pages_to_audio.domain.enums.roles import ActorType
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.domain.state_machine import transition_session
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


class WorkflowStarter(Protocol):
    async def start_process_exam(self, session_public_id: str) -> None: ...


class NoOpWorkflowStarter:
    """Placeholder until Phase 4 — records event, no actual workflow."""

    async def start_process_exam(self, session_public_id: str) -> None:
        logger.info("workflow_start_noop", session_id=session_public_id)


async def lock_session(
    uow: Any,
    session: Any,
    end_reason: EndReason,
    workflow_starter: WorkflowStarter,
    *,
    config_snapshot: dict | None = None,
    provider_snapshot: dict | None = None,
) -> Any:
    """
    Execute LOCK_SESSION atomically in a single transaction (§3.7.1):
    1. Confirm end_reason
    2. status → CAPTURE_LOCKING
    3. Validate captures (no pending bursts)
    4. Close frame set
    5. Create snapshots
    6. status → LOCKED
    7. Start ProcessExamWorkflow (via port)
    """
    now = datetime.now(UTC)

    # Step 2: CAPTURE_LOCKING
    await transition_session(
        uow,
        session,
        SessionState.CAPTURE_LOCKING,
        reason=ReasonCode.SESSION_LOCKED,
        actor=ActorType.SYSTEM,
        payload={"end_reason": end_reason},
    )

    # Step 5: Record snapshots
    session.config_snapshot = config_snapshot or {}
    session.provider_snapshot = provider_snapshot or {"locked_at": now.isoformat()}
    session.capture_locked_at = now
    session.end_reason = end_reason
    await uow.session.flush()

    # Step 6: LOCKED
    await transition_session(
        uow,
        session,
        SessionState.LOCKED,
        reason=None,
        actor=ActorType.SYSTEM,
    )

    await uow.commit()

    # Step 7: Start workflow (idempotent by workflow_id)
    await workflow_starter.start_process_exam(session.public_id)

    return session
