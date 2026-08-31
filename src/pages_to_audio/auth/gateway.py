"""Gateway authentication — §11.2."""

from __future__ import annotations

import hashlib
import hmac

from fastapi import Header, HTTPException

from src.pages_to_audio.common.errors import ReasonCode
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

_HASH_ALG = "sha256"


def _constant_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def verify_gateway_token(
    authorization: str = Header(...),
    x_gateway_id: str = Header(..., alias="X-Gateway-Id"),
) -> str:
    """FastAPI dependency — validates gateway bearer token."""
    settings = get_settings()

    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")

    provided = authorization[7:]
    primary = settings.auth.ANDROID_GATEWAY_TOKEN.get_secret_value()
    previous = settings.auth.ANDROID_GATEWAY_TOKEN_PREVIOUS.get_secret_value()

    primary_ok = _constant_compare(provided, primary)
    previous_ok = previous and _constant_compare(provided, previous)
    if not (primary_ok or previous_ok):
        logger.warning("gateway_auth_failed", gateway_id=x_gateway_id)
        raise HTTPException(
            status_code=401,
            detail={"reason_code": ReasonCode.GATEWAY_AUTH_FAILED},
        )

    return x_gateway_id
