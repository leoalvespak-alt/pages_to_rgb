#!/usr/bin/env python3
"""Bootstrap Supabase storage buckets — idempotent — §2.1.8."""

from __future__ import annotations

import asyncio

import httpx

from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)

BUCKETS = [
    "pages-originals",
    "pages-derived",
    "ocr-raw",
    "knowledge",
    "audio",
    "audit-exports",
]


async def bootstrap() -> None:
    configure_logging()
    settings = get_settings()
    url = settings.supabase.URL.rstrip("/")
    key = settings.supabase.SERVICE_ROLE_KEY.get_secret_value()
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=10) as client:
        for bucket in BUCKETS:
            r = await client.post(
                f"{url}/storage/v1/bucket",
                json={"id": bucket, "name": bucket, "public": False},
                headers=headers,
            )
            if r.status_code in (200, 201):
                logger.info("bucket_created", bucket=bucket)
            elif r.status_code == 409:
                logger.info("bucket_exists", bucket=bucket)
            else:
                logger.error("bucket_error", bucket=bucket, status=r.status_code)


if __name__ == "__main__":
    asyncio.run(bootstrap())
