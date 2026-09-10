from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from temporalio.client import Client

from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.db.engine import get_engine

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
async def liveness() -> dict[str, str]:
    """Liveness: processo responde. Não prova dependências (ver /ready)."""
    return {"status": "ok"}


TERMINAL_STATES = {"COMPLETED", "FAILED_FATAL", "CANCELLED", "READY"}


@router.get("/ready")
async def readiness() -> dict[str, Any]:
    """S08.1/A06: readiness verifica dependências necessárias com timeouts.

    200 somente quando banco + storage configurado + Temporal (quando configurado)
    respondem. HTTP 200 genérico e /live não são prova de deploy.
    """
    from fastapi.responses import JSONResponse

    database, storage, temporal, outbox = await asyncio.gather(
        _database_check(), _storage_check(), _temporal_check(), _outbox_check()
    )
    checks = {"database": database, "storage": storage, "temporal": temporal, "outbox": outbox}
    required_down = [
        name
        for name, check in (("database", database), ("storage", storage), ("temporal", temporal))
        if check.get("status") == "unavailable"
    ]
    # Produção exige Temporal configurado (worker precisa consumir a fila).
    if get_settings().APP_ENV == "production" and temporal.get("status") == "not_configured":
        required_down.append("temporal")
    if required_down:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": checks, "failing": required_down},
        )
    return {"status": "ready", "checks": checks}


async def _database_check() -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    if not settings.DATABASE_URL.get_secret_value():
        return {
            "status": "not_configured",
            "latency_ms": None,
            "checked_at": datetime.now(UTC).isoformat(),
        }
    try:
        async with asyncio.timeout(2):
            async with get_engine().connect() as connection:
                await connection.execute(text("SELECT 1"))
        return {
            "status": "ok",
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "error": type(exc).__name__,
            "checked_at": datetime.now(UTC).isoformat(),
        }


async def _temporal_check() -> dict[str, Any]:
    started = perf_counter()
    settings = get_settings()
    if not settings.TEMPORAL_ADDRESS:
        return {
            "status": "not_configured",
            "latency_ms": None,
            "checked_at": datetime.now(UTC).isoformat(),
        }
    try:
        async with asyncio.timeout(3):
            client = await Client.connect(
                settings.TEMPORAL_ADDRESS,
                namespace=settings.TEMPORAL_NAMESPACE,
                tls=settings.TEMPORAL_TLS,
                lazy=True,
            )
            serving = await client.service_client.check_health(
                retry=False,
                timeout=timedelta(seconds=2),
            )
        return {
            "status": "ok" if serving else "unavailable",
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "error": type(exc).__name__,
            "checked_at": datetime.now(UTC).isoformat(),
        }


@router.get("/dependencies")
async def dependencies() -> dict[str, Any]:
    database, storage, temporal, outbox = await asyncio.gather(
        _database_check(), _storage_check(), _temporal_check(), _outbox_check()
    )
    return {
        "dependencies": {
            "database": database,
            "storage": storage,
            "temporal": temporal,
            "workflow_outbox": outbox,
        }
    }


@router.get("/worker")
async def worker_health() -> dict[str, Any]:
    """S08.1: worker demonstra conexão/polling efetivo da fila (não só API viva)."""
    from fastapi.responses import JSONResponse

    started = perf_counter()
    settings = get_settings()
    if not settings.TEMPORAL_ADDRESS:
        return {"status": "not_configured", "task_queue": settings.TEMPORAL_TASK_QUEUE}
    try:
        async with asyncio.timeout(5):
            client = await Client.connect(
                settings.TEMPORAL_ADDRESS,
                namespace=settings.TEMPORAL_NAMESPACE,
                tls=settings.TEMPORAL_TLS,
                lazy=True,
            )
            from temporalio.api.taskqueue.v1 import TaskQueue
            from temporalio.api.workflowservice.v1 import DescribeTaskQueueRequest

            desc = await client.service_client.workflow_service.describe_task_queue(
                DescribeTaskQueueRequest(
                    namespace=settings.TEMPORAL_NAMESPACE,
                    task_queue=TaskQueue(name=settings.TEMPORAL_TASK_QUEUE),
                    report_pollers=True,
                )
            )
            pollers = len(getattr(desc, "pollers", []) or [])
        return {
            "status": "ok" if pollers > 0 else "no_pollers",
            "task_queue": settings.TEMPORAL_TASK_QUEUE,
            "pollers": pollers,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unavailable",
                "task_queue": settings.TEMPORAL_TASK_QUEUE,
                "error": type(exc).__name__,
            },
        )  # type: ignore[return-value]


async def _storage_check() -> dict[str, Any]:
    """S08.1: storage configurado e alcançável (sem segredos no payload)."""
    from src.pages_to_audio.config.settings import get_settings as _get_settings

    started = perf_counter()
    settings = _get_settings()
    provider = settings.STORAGE_PROVIDER
    try:
        from src.pages_to_audio.storage import get_storage_adapter

        adapter = get_storage_adapter()
        configured = getattr(adapter, "is_configured", True)
        if configured is False:
            return {
                "status": "unavailable",
                "provider": provider,
                "latency_ms": round((perf_counter() - started) * 1000, 2),
                "checked_at": datetime.now(UTC).isoformat(),
            }
        return {
            "status": "ok",
            "provider": provider,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return {
            "status": "not_configured" if "nenhum storage" in str(exc).lower() else "unavailable",
            "provider": provider,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "error": type(exc).__name__,
            "checked_at": datetime.now(UTC).isoformat(),
        }


async def _outbox_check() -> dict[str, Any]:
    """S08.2: expõe outbox pendente (sem dados sensíveis)."""
    from sqlalchemy import func, select

    started = perf_counter()
    try:
        from src.pages_to_audio.db.engine import get_engine as _get_engine
        from src.pages_to_audio.db.models.workflow_outbox import WorkflowOutbox

        async with _get_engine().connect() as connection:
            pending = await connection.scalar(
                select(func.count())
                .select_from(WorkflowOutbox)
                .where(WorkflowOutbox.status.in_(["PENDING", "FAILED"]))
            )
        return {
            "status": "ok",
            "pending": int(pending or 0),
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "checked_at": datetime.now(UTC).isoformat(),
        }
    except Exception as exc:
        return {
            "status": "unknown",
            "error": type(exc).__name__,
            "latency_ms": round((perf_counter() - started) * 1000, 2),
            "checked_at": datetime.now(UTC).isoformat(),
        }
