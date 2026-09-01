from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, cast

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Header, HTTPException, Request
from jose import JWTError, jwt  # type: ignore[import-untyped]

from src.pages_to_audio.config.settings import AppSettings, get_settings

COOKIE_NAME = "admin_session"
ALGORITHM = "HS256"
_attempts: dict[str, deque[float]] = defaultdict(deque)
_hasher = PasswordHasher()


def verify_admin_password(password: str, settings: AppSettings) -> bool:
    if not settings.ADMIN_PASSWORD_HASH:
        return False
    try:
        return bool(_hasher.verify(settings.ADMIN_PASSWORD_HASH, password))
    except (VerifyMismatchError, InvalidHashError):
        return False


def enforce_login_rate_limit(client_key: str, settings: AppSettings) -> None:
    now = time.monotonic()
    window = settings.ADMIN_LOGIN_WINDOW_SECONDS
    attempts = _attempts[client_key]
    while attempts and now - attempts[0] > window:
        attempts.popleft()
    if len(attempts) >= settings.ADMIN_LOGIN_MAX_ATTEMPTS:
        raise HTTPException(status_code=429, detail="Too many login attempts")
    attempts.append(now)


def clear_login_attempts(client_key: str) -> None:
    _attempts.pop(client_key, None)


def _csrf_signature(nonce: str, settings: AppSettings) -> str:
    secret = settings.CSRF_SECRET.get_secret_value()
    if not secret:
        raise HTTPException(status_code=503, detail="Admin authentication is not configured")
    return hmac.new(secret.encode(), nonce.encode(), hashlib.sha256).hexdigest()


def create_admin_token(settings: AppSettings) -> tuple[str, str, datetime]:
    secret = settings.SESSION_SECRET.get_secret_value()
    if not secret or not settings.CSRF_SECRET.get_secret_value():
        raise HTTPException(status_code=503, detail="Admin authentication is not configured")
    now = datetime.now(UTC)
    expires = now + timedelta(days=settings.ADMIN_SESSION_TTL_DAYS)
    nonce = secrets.token_urlsafe(24)
    csrf = f"{nonce}.{_csrf_signature(nonce, settings)}"
    token = jwt.encode(
        {
            "sub": "admin",
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": secrets.token_urlsafe(18),
            "csrf": csrf,
            "ver": 1,
        },
        secret,
        algorithm=ALGORITHM,
    )
    return token, csrf, expires


def decode_admin_token(token: str, settings: AppSettings) -> dict[str, Any]:
    secret = settings.SESSION_SECRET.get_secret_value()
    if not secret:
        raise HTTPException(status_code=503, detail="Admin authentication is not configured")
    try:
        claims = cast(dict[str, Any], jwt.decode(token, secret, algorithms=[ALGORITHM]))
    except JWTError as exc:
        raise HTTPException(status_code=401, detail="Invalid admin session") from exc
    if claims.get("sub") != "admin" or claims.get("ver") != 1:
        raise HTTPException(status_code=401, detail="Invalid admin session")
    return claims


async def require_admin_session(request: Request) -> dict[str, Any]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Admin session required")
    return decode_admin_token(token, get_settings())


AdminClaimsDep = Annotated[dict[str, Any], Depends(require_admin_session)]


async def require_admin_csrf(
    claims: AdminClaimsDep,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> dict[str, Any]:
    expected = claims.get("csrf")
    if (
        not isinstance(expected, str)
        or not x_csrf_token
        or not secrets.compare_digest(expected, x_csrf_token)
    ):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    nonce, separator, signature = x_csrf_token.partition(".")
    if not separator or not hmac.compare_digest(signature, _csrf_signature(nonce, get_settings())):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return claims


AdminCsrfDep = Annotated[dict[str, Any], Depends(require_admin_csrf)]


def reset_admin_rate_limits() -> None:
    _attempts.clear()
