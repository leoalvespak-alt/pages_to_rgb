"""S02.10 — solicitação de cancelamento do workflow Temporal."""

from __future__ import annotations

from src.pages_to_audio.capture.dispatcher import workflow_id_for
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.client import get_temporal_client

logger = get_logger(__name__)


async def request_workflow_cancellation(session_public_id: str) -> bool:
    """Cancela o workflow process-exam-{public_id} se existir. Idempotente."""
    try:
        client = await get_temporal_client()
    except Exception as exc:
        logger.warning("cancel_no_temporal", error=str(exc)[:200], session_id=session_public_id)
        return False
    try:
        handle = client.get_workflow_handle(workflow_id_for(session_public_id))
        await handle.cancel()
        logger.info("workflow_cancel_requested", session_id=session_public_id)
        return True
    except Exception as exc:
        logger.warning("workflow_cancel_failed", error=str(exc)[:200], session_id=session_public_id)
        return False
