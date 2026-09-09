"""S02.9 — dispatcher do outbox de workflow (idempotente, retry observável)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.db.models.workflow_outbox import WorkflowOutbox
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.starter import WORKFLOW_ID_PREFIX

logger = get_logger(__name__)


def workflow_id_for(session_public_id: str) -> str:
    return f"{WORKFLOW_ID_PREFIX}-{session_public_id}"


async def enqueue_workflow_intent(
    db: AsyncSession, *, session_db_id: object, session_public_id: str
) -> WorkflowOutbox:
    """Grava intenção na MESMA transação do LOCK (chamador faz flush/commit)."""
    row = await db.scalar(
        select(WorkflowOutbox).where(WorkflowOutbox.session_id == session_db_id).with_for_update()  # type: ignore[arg-type]
    )
    if row is not None:
        return row
    row = WorkflowOutbox(
        session_id=session_db_id,  # type: ignore[arg-type]
        workflow_id=workflow_id_for(session_public_id),
        status="PENDING",
    )
    db.add(row)
    await db.flush()
    return row


async def dispatch_pending(db: AsyncSession, *, limit: int = 20) -> dict[str, int]:
    """Envia intents PENDING/FAILED com workflow_id determinístico.

    Chamado por worker/cron após commit do LOCK. AlreadyStarted = idempotente.
    Retorna contadores (sem segredos).
    """
    from src.pages_to_audio.workflows.starter import TemporalWorkflowStarter

    rows = (
        (
            await db.execute(
                select(WorkflowOutbox)
                .where(WorkflowOutbox.status.in_(["PENDING", "FAILED"]))
                .order_by(WorkflowOutbox.created_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        .scalars()
        .all()
    )
    dispatched = 0
    failed = 0
    starter = TemporalWorkflowStarter()
    for row in rows:
        try:
            # starter usa id determinístico; repetição é no-op no Temporal.
            await starter.start_process_exam_by_workflow_id(row.workflow_id)
            row.status = "DISPATCHED"
            row.dispatched_at = datetime.now(UTC)
            dispatched += 1
        except Exception as exc:
            row.status = "FAILED"
            row.attempts = int(row.attempts or 0) + 1
            row.last_error = str(exc)[:500]
            failed += 1
            logger.warning(
                "workflow_dispatch_failed", workflow_id=row.workflow_id, error=str(exc)[:200]
            )
    await db.flush()
    return {"dispatched": dispatched, "failed": failed}
