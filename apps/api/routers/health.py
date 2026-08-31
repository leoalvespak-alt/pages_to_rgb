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
    return {"status": "ok"}


@router.get("/ready")
async def readiness() -> dict[str, Any]:
    return {"status": "ready", "checks": {}}


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
    database, temporal = await asyncio.gather(_database_check(), _temporal_check())
    return {
        "dependencies": {
            "database": database,
            "supabase_storage": {
                "status": "not_configured",
                "latency_ms": None,
                "checked_at": datetime.now(UTC).isoformat(),
            },
            "temporal": temporal,
        }
    }
