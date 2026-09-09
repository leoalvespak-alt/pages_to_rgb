#!/usr/bin/env python3
"""Reconcile orphaned storage objects — §2.5.1 (S02.11: reconciliação real).

Delega para src/pages_to_audio/capture/orphans.py. Idempotente e seguro para
rodar repetido.
"""

from __future__ import annotations

import asyncio
import sys

from src.pages_to_audio.capture.orphans import reconcile
from src.pages_to_audio.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)


async def _main() -> int:
    configure_logging()
    logger.info("storage_reconciliation_start")
    try:
        stats = await reconcile()
    except Exception as exc:
        logger.warning("storage_reconciliation_failed", error=str(exc)[:200])
        return 1
    logger.info("storage_reconciliation_complete", **stats)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
