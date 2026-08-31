"""Temporary file manager — §5.1, §18.4."""

from __future__ import annotations

import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)


def _session_temp_dir(session_id: str) -> Path:
    settings = get_settings()
    return Path(settings.LOCAL_TEMP_ROOT) / session_id


def _total_usage_gb(root: Path) -> float:
    if not root.exists():
        return 0.0
    total = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    return total / (1024**3)


@asynccontextmanager
async def session_temp_dir(session_id: str) -> AsyncGenerator[Path, None]:
    """Context manager yielding a per-session temp dir, always cleaned in finally.

    Enforces LOCAL_TEMP_MAX_GB quota: if exceeded, logs an alert and still
    yields (caller must skip non-essential derivatives, §18.4).
    """
    settings = get_settings()
    root = Path(settings.LOCAL_TEMP_ROOT)
    session_dir = root / session_id

    session_dir.mkdir(parents=True, exist_ok=True)
    usage = _total_usage_gb(root)
    if usage >= settings.LOCAL_TEMP_MAX_GB:
        logger.warning(
            "temp_quota_exceeded",
            usage_gb=round(usage, 3),
            limit_gb=settings.LOCAL_TEMP_MAX_GB,
            session_id=session_id,
        )
    try:
        yield session_dir
    finally:
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
            logger.debug("temp_dir_cleaned", session_id=session_id)


def cleanup_expired_sessions(ttl_hours: int | None = None) -> int:
    """Remove session temp dirs older than TTL. Returns count removed."""
    import time

    settings = get_settings()
    root = Path(settings.LOCAL_TEMP_ROOT)
    hours = ttl_hours if ttl_hours is not None else settings.LOCAL_TEMP_TTL_HOURS
    cutoff = time.time() - (hours * 3600)
    removed = 0

    if not root.exists():
        return 0

    for child in root.iterdir():
        if child.is_dir():
            mtime = child.stat().st_mtime
            if mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                removed += 1
                logger.info("temp_dir_expired_cleaned", path=str(child))

    return removed
