"""Frame upload pipeline — §12.3."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.common.errors import (
    FrameConflictError,
    NonRetryableError,
    ReasonCode,
    StorageError,
)
from src.pages_to_audio.db.models.capture import Capture
from src.pages_to_audio.db.models.frame import Frame
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.domain.ports.storage import StoragePort
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.storage.keys import frame_key

logger = get_logger(__name__)

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}

MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
}

MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10 MB


@dataclass
class FrameUploadRequest:
    session_id: str
    capture_id: str
    frame_index: int
    declared_sha256: str
    data: bytes
    mime_type: str
    received_android_at: str | None = None
    capture_source: str = "ANDROID_CAMERA"
    android_orientation: int | None = None
    source_resolution: str | None = None
    width: int | None = None
    height: int | None = None


@dataclass
class FrameUploadResult:
    frame_db_id: str
    storage_key: str
    sha256: str
    size_bytes: int
    duplicate: bool = False


def _validate_mime(data: bytes, mime_type: str) -> None:
    if mime_type not in ALLOWED_MIMES:
        raise NonRetryableError(
            f"Invalid MIME type: {mime_type}",
            reason_code=ReasonCode.FRAME_INVALID_MIME,
            http_status=415,
        )
    expected_magics = MAGIC_BYTES.get(mime_type, [])
    if not any(data.startswith(m) for m in expected_magics):
        raise NonRetryableError(
            "Magic bytes do not match declared MIME type",
            reason_code=ReasonCode.FRAME_INVALID_MAGIC_BYTES,
            http_status=415,
        )


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_received_at(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        iso = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


async def upload_frame(
    request: FrameUploadRequest,
    storage: StoragePort,
    db_session: AsyncSession,
) -> FrameUploadResult:
    """Execute mandatory §12.3 flow: validate, SHA-256, guard, capture, idempotency, storage, DB."""

    # Validate MIME and magic bytes
    _validate_mime(request.data, request.mime_type)

    # Validate size
    if len(request.data) > MAX_FRAME_SIZE:
        raise NonRetryableError(
            f"Frame too large: {len(request.data)} bytes",
            reason_code=ReasonCode.FRAME_TOO_LARGE,
            http_status=413,
        )

    # Compute and verify SHA-256
    actual_sha256 = _compute_sha256(request.data)
    if actual_sha256 != request.declared_sha256:
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_HASH_MISMATCH,
            message=f"SHA-256 mismatch: declared={request.declared_sha256} actual={actual_sha256}",
        )

    # Check session exists and is not terminal
    result = await db_session.execute(
        select(Session).where(Session.public_id == request.session_id).with_for_update()
    )
    session_obj = result.scalar_one_or_none()
    if session_obj is None:
        raise NonRetryableError(
            f"Session not found: {request.session_id}",
            reason_code=ReasonCode.SESSION_NOT_FOUND,
            http_status=404,
        )
    if SessionState(session_obj.status).is_terminal:
        raise FrameConflictError(
            reason_code=ReasonCode.SESSION_LOCKED,
            message="Session is locked or terminal — frame rejected",
        )

    # Resolve Capture — create if not exists with capture_source
    capture_source = request.capture_source
    if capture_source not in ("ANDROID_CAMERA", "ESP32_CAMERA"):
        capture_source = "ANDROID_CAMERA"
    cap_result = await db_session.execute(
        select(Capture)
        .where(Capture.session_id == session_obj.id, Capture.capture_id == request.capture_id)
        .with_for_update()
    )
    capture_obj = cap_result.scalar_one_or_none()
    if capture_obj is None:
        capture_obj = Capture(
            session_id=session_obj.id,
            capture_id=request.capture_id,
            mode="full",
            command_cursor=0,
            requested_frames=0,
            received_frames=0,
            status="open",
            capture_source=capture_source,
            session_type=getattr(session_obj, "session_type", "EXAM") or "EXAM",
        )
        db_session.add(capture_obj)
        await db_session.flush()

    # Idempotency: same capture_id + frame_index
    existing_result = await db_session.execute(
        select(Frame).where(
            Frame.capture_id == capture_obj.id,
            Frame.frame_index == request.frame_index,
        )
    )
    existing_frame = existing_result.scalar_one_or_none()
    if existing_frame is not None:
        if existing_frame.sha256 == actual_sha256:
            logger.info(
                "frame_idempotent_hit",
                session_id=request.session_id,
                capture_id=request.capture_id,
                frame_index=request.frame_index,
                sha256=actual_sha256,
            )
            return FrameUploadResult(
                frame_db_id=str(existing_frame.id),
                storage_key=existing_frame.storage_key,
                sha256=actual_sha256,
                size_bytes=len(request.data),
                duplicate=True,
            )
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_DUPLICATE_CONFLICT,
            message=f"Frame index {request.frame_index} already exists with different sha256",
        )

    # Additional idempotency via session_id+sha256+capture_id+frame_index
    dup_result = await db_session.execute(
        select(Frame).where(
            Frame.session_id == session_obj.id,
            Frame.sha256 == actual_sha256,
            Frame.capture_id == capture_obj.id,
            Frame.frame_index == request.frame_index,
        )
    )
    dup_frame = dup_result.scalar_one_or_none()
    if dup_frame is not None:
        return FrameUploadResult(
            frame_db_id=str(dup_frame.id),
            storage_key=dup_frame.storage_key,
            sha256=actual_sha256,
            size_bytes=len(request.data),
            duplicate=True,
        )

    # Upload to storage (overwrite=False — never overwrite originals)
    storage_key = frame_key(request.session_id, request.capture_id, request.frame_index)
    try:
        await storage.put_object(
            "pages-originals",
            storage_key,
            request.data,
            request.mime_type,
            sha256=actual_sha256,
            overwrite=False,
        )
    except StorageError:
        logger.warning(
            "frame_storage_failed",
            session_id=request.session_id,
            capture_id=request.capture_id,
            frame_index=request.frame_index,
        )
        raise

    # Insert Frame
    received_at = _parse_received_at(request.received_android_at)
    frame = Frame(
        session_id=session_obj.id,
        capture_id=capture_obj.id,
        frame_index=request.frame_index,
        sha256=actual_sha256,
        content_length=len(request.data),
        mime_type=request.mime_type,
        width=request.width,
        height=request.height,
        storage_key=storage_key,
        received_android_at=received_at,
        capture_source=capture_source,
        android_orientation=request.android_orientation,
        source_resolution=request.source_resolution,
        status="accepted",
    )
    db_session.add(frame)
    capture_obj.received_frames = int(capture_obj.received_frames or 0) + 1
    await db_session.flush()
    await db_session.refresh(frame)

    logger.info(
        "frame_uploaded",
        session_id=request.session_id,
        capture_id=request.capture_id,
        frame_index=request.frame_index,
        sha256=actual_sha256,
        storage_key=storage_key,
        frame_id=str(frame.id),
    )
    return FrameUploadResult(
        frame_db_id=str(frame.id),
        storage_key=storage_key,
        sha256=actual_sha256,
        size_bytes=len(request.data),
    )
