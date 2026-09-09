"""Temporal worker — §4.2."""

from __future__ import annotations

import asyncio
import concurrent.futures

from temporalio.client import Client
from temporalio.worker import Worker

from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.activities.real import REAL_ACTIVITIES
from src.pages_to_audio.workflows.activities.rgb import (
    mark_rgb_result_processing,
    publish_rgb_result,
)
from src.pages_to_audio.workflows.client import get_temporal_client
from src.pages_to_audio.workflows.process_exam import ProcessExamWorkflow

logger = get_logger(__name__)


async def run_worker(settings: AppSettings | None = None) -> None:
    cfg = settings or get_settings()
    client: Client = await get_temporal_client(cfg)

    # Separate executor for CPU-bound image/OCR activities (§4.2.2)
    cpu_executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=max(
            cfg.MAX_IMAGE_PROCESSING_CONCURRENCY,
            cfg.MAX_LLM_CONCURRENCY,
        ),
        thread_name_prefix="pages-cpu",
    )

    worker = Worker(
        client,
        task_queue=cfg.TEMPORAL_TASK_QUEUE,
        workflows=[ProcessExamWorkflow],
        activities=[
            # S05.1: registro operacional SOMENTE com atividades reais.
            # Fakes vivem só em tests/workflows isolados.
            *REAL_ACTIVITIES,
            mark_rgb_result_processing,
            publish_rgb_result,
        ],
        activity_executor=cpu_executor,
        # Concurrency limits from §44
        max_concurrent_activities=cfg.MAX_LLM_CONCURRENCY,
        max_concurrent_workflow_tasks=10,
    )

    logger.info(
        "temporal_worker_starting",
        task_queue=cfg.TEMPORAL_TASK_QUEUE,
        namespace=cfg.TEMPORAL_NAMESPACE,
    )
    # S02.9/A04: loop de despacho do outbox — intents PENDING/FAILED de fechamentos
    # com Temporal indisponível são enviados com retry observável (30 s).
    stop_dispatch = asyncio.Event()

    async def _dispatch_loop() -> None:
        from src.pages_to_audio.capture.dispatcher import dispatch_pending
        from src.pages_to_audio.db.uow import UnitOfWork

        while not stop_dispatch.is_set():
            try:
                async with UnitOfWork() as uow:
                    stats = await dispatch_pending(uow.session)
                    await uow.commit()
                if stats["dispatched"] or stats["failed"]:
                    logger.info("workflow_outbox_dispatch", **stats)
            except Exception as exc:
                logger.warning("workflow_outbox_dispatch_failed", error=str(exc)[:200])
            try:
                await asyncio.wait_for(stop_dispatch.wait(), timeout=30.0)
            except TimeoutError:
                continue

    dispatch_task = asyncio.create_task(_dispatch_loop())
    try:
        await worker.run()
    finally:
        stop_dispatch.set()
        dispatch_task.cancel()
        cpu_executor.shutdown(wait=False)
        logger.info("temporal_worker_stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
