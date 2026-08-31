"""Device attestation — §11.3."""

from __future__ import annotations

import hashlib
import hmac
import time

from src.pages_to_audio.common.errors import AuthError, ReasonCode
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

# Nonces seen in current replay window — in production use Redis or DB
_seen_nonces: dict[str, float] = {}


def _derive_device_key(master_key: bytes, device_id: str) -> bytes:
    return hmac.new(master_key, device_id.encode(), hashlib.sha256).digest()


def verify_device_hmac(
    *,
    device_id: str,
    capture_id: str,
    frame_index: int,
    sha256: str,
    timestamp: int,
    nonce: str,
    provided_hmac: str,
) -> None:
    """Verify HMAC attestation from the Android gateway for a device frame upload."""
    settings = get_settings()
    master_key = settings.auth.DEVICE_HMAC_MASTER_KEY.get_secret_value().encode()
    window = settings.auth.DEVICE_REPLAY_WINDOW_SECONDS

    now = int(time.time())
    if abs(now - timestamp) > window:
        raise AuthError(
            "Device timestamp outside replay window",
            reason_code=ReasonCode.DEVICE_AUTH_FAILED,
        )

    if nonce in _seen_nonces:
        raise AuthError("Replay detected", reason_code=ReasonCode.DEVICE_REPLAY_DETECTED)

    device_key = _derive_device_key(master_key, device_id)
    message = f"{device_id}:{capture_id}:{frame_index}:{sha256}:{timestamp}:{nonce}".encode()
    expected = hmac.new(device_key, message, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(provided_hmac, expected):
        raise AuthError("Invalid device HMAC", reason_code=ReasonCode.DEVICE_AUTH_FAILED)

    # Record nonce to prevent replay
    _seen_nonces[nonce] = now
    # Purge old nonces
    cutoff = now - window
    for k in [k for k, v in _seen_nonces.items() if v < cutoff]:
        del _seen_nonces[k]
