"""Real WorkflowStarter — replaces NoOpWorkflowStarter from Phase 3.

Workflow ID is deterministic: process-exam-{session_public_id}.
Calling start twice with the same ID is a no-op (Temporal dedup).
"""

from __future__ import annotations

from temporalio.client import Client
from temporalio.service import RPCError

from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.client import get_temporal_client
from src.pages_to_audio.workflows.process_exam import ProcessExamWorkflow

logger = get_logger(__name__)

WORKFLOW_ID_PREFIX = "process-exam"


def _workflow_id(session_public_id: str) -> str:
    return f"{WORKFLOW_ID_PREFIX}-{session_public_id}"


class TemporalWorkflowStarter:
    """Real implementation of the WorkflowStarter port (§3.7.2 / §4.1.3)."""

    def __init__(self, client: Client | None = None) -> None:
        self._client = client

    async def _get_client(self) -> Client:
        if self._client is not None:
            return self._client
        return await get_temporal_client()

    async def start_process_exam(
        self, session_public_id: str, *, operation_suffix: str | None = None
    ) -> None:
        client = await self._get_client()
        wf_id = _workflow_id(session_public_id)
        if operation_suffix:
            wf_id = f"{wf_id}-retry-{operation_suffix}"
        try:
            handle = await client.start_workflow(
                ProcessExamWorkflow.run,
                session_public_id,
                id=wf_id,
                task_queue=client._config.get("task_queue", "pages-to-audio-main"),  # type: ignore[attr-defined]
            )
            logger.info(
                "workflow_started",
                workflow_id=wf_id,
                run_id=handle.result_run_id,
                session_id=session_public_id,
            )
        except RPCError as exc:
            if "already started" in str(exc).lower():
                logger.info("workflow_already_started", workflow_id=wf_id)
            else:
                raise
