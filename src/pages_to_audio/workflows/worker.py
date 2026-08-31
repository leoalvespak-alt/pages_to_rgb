"""Temporal worker — §4.2."""

from __future__ import annotations

import asyncio
import concurrent.futures

from temporalio.client import Client
from temporalio.worker import Worker

from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.workflows.activities.fakes import ALL_FAKE_ACTIVITIES
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
            *ALL_FAKE_ACTIVITIES,
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
    try:
        await worker.run()
    finally:
        cpu_executor.shutdown(wait=False)
        logger.info("temporal_worker_stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
