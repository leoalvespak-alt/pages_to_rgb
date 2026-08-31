"""Idempotency service — §14."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from src.pages_to_audio.common.errors import NonRetryableError, ReasonCode
from src.pages_to_audio.db.models.idempotency_key import IdempotencyKey


def _canonical_hash(body: bytes | str | dict, params: dict | None = None) -> str:
    if isinstance(body, dict):
        body = json.dumps(body, sort_keys=True).encode()
    elif isinstance(body, str):
        body = body.encode()
    data = body
    if params:
        data += json.dumps(params, sort_keys=True).encode()
    return hashlib.sha256(data).hexdigest()


class IdempotencyConflictError(NonRetryableError):
    def __init__(self) -> None:
        super().__init__(
            "Idempotency key reused with different payload",
            reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD,
            http_status=409,
        )


class IdempotencyService:
    def __init__(self, ttl_hours: int = 48) -> None:
        self._ttl_hours = ttl_hours

    async def check_and_store(
        self,
        session,  # SQLAlchemy AsyncSession
        *,
        key: str,
        scope: str,
        request_hash: str,
    ) -> IdempotencyKey | None:
        """Return existing record if key found; None if new (caller must call record_response)."""
        result = await session.execute(
            select(IdempotencyKey).where(
                IdempotencyKey.key == key,
                IdempotencyKey.scope == scope,
            )
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            now = datetime.now(UTC)
            if existing.expires_at.replace(tzinfo=UTC) < now:
                # Expired — delete and treat as new
                await session.delete(existing)
                return None
            if existing.request_hash != request_hash:
                raise IdempotencyConflictError()
            return existing

        return None

    async def record_response(
        self,
        session,  # SQLAlchemy AsyncSession
        *,
        key: str,
        scope: str,
        request_hash: str,
        response_status: int,
        response_body: str,
    ) -> None:
        expires_at = datetime.now(UTC) + timedelta(hours=self._ttl_hours)
        record = IdempotencyKey(
            key=key,
            scope=scope,
            request_hash=request_hash,
            response_status=response_status,
            response_body=response_body,
            expires_at=expires_at,
        )
        session.add(record)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()

    async def cleanup_expired(self, session) -> int:  # type: ignore[return]
        now = datetime.now(UTC)
        result = await session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.expires_at < now)
        )
        return result.rowcount  # type: ignore[return-value]


def compute_request_hash(body: bytes | str | dict, params: dict | None = None) -> str:
    return _canonical_hash(body, params)
