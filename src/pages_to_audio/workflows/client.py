"""Temporal client factory — §2.3, §4.1."""

from __future__ import annotations

from temporalio.client import Client, TLSConfig

from src.pages_to_audio.config.settings import AppSettings, get_settings
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_client: Client | None = None


async def get_temporal_client(settings: AppSettings | None = None) -> Client:
    """Return a singleton Temporal client. Thread-safe for asyncio."""
    global _client
    if _client is not None:
        return _client

    cfg = settings or get_settings()
    address = cfg.TEMPORAL_ADDRESS
    namespace = cfg.TEMPORAL_NAMESPACE
    tls: TLSConfig | bool = cfg.TEMPORAL_TLS

    logger.info("temporal_client_connecting", address=address, namespace=namespace)

    _client = await Client.connect(
        address,
        namespace=namespace,
        tls=tls,
    )
    logger.info("temporal_client_connected")
    return _client


async def close_temporal_client() -> None:
    global _client
    if _client is not None:
        _client = None
        logger.info("temporal_client_closed")
