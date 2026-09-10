"""Frame upload pipeline — §12.3."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.capture.derivatives import persist_ocr_derivative
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
from src.pages_to_audio.storage.keys import derived_key, frame_key

logger = get_logger(__name__)

ALLOWED_MIMES = {"image/jpeg", "image/png", "image/webp"}

MAGIC_BYTES: dict[str, list[bytes]] = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
}

MAX_FRAME_SIZE = 10 * 1024 * 1024  # 10 MB

# S02.7/A10: estados que ainda permitem anexação de frames NOVOS.
# LOCKED e todo processamento posterior são fechados; duplicata idempotente de
# frame já conhecido continua permitida (verificada antes da rejeição).
UPLOAD_OPEN_STATES = frozenset(
    {
        SessionState.CAPTURING,
        SessionState.CAPTURE_END_CANDIDATE,
        SessionState.CAPTURE_LOCKING,
    }
)

MIN_JPEG_DIM = 64
MAX_JPEG_DIM = 8192


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
    page_number: int | None = None
    frame_number: int | None = None


@dataclass
class FrameUploadResult:
    frame_db_id: str
    storage_key: str
    sha256: str
    size_bytes: int
    duplicate: bool = False
    derived_storage_key: str | None = None


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


def _validate_image_content(data: bytes, mime_type: str) -> tuple[int | None, int | None]:
    """S01.5/A19: decodifica a imagem real (nao apenas magic bytes).

    Retorna (width, height) do conteudo decodificado. Rejeita 415 se truncada
    ou falsa; 422 se dimensoes fora de [64, 8192].
    """
    try:
        from io import BytesIO

        from PIL import Image
    except ImportError as exc:
        raise NonRetryableError(
            "Image decoder unavailable",
            reason_code=ReasonCode.FRAME_INVALID_MAGIC_BYTES,
            http_status=500,
        ) from exc
    try:
        with Image.open(BytesIO(data)) as img:
            img.load()
            width, height = int(img.width), int(img.height)
    except Exception as exc:
        raise NonRetryableError(
            "File is not a decodable image",
            reason_code=ReasonCode.FRAME_INVALID_MAGIC_BYTES,
            http_status=415,
        ) from exc
    if not (MIN_JPEG_DIM <= width <= MAX_JPEG_DIM and MIN_JPEG_DIM <= height <= MAX_JPEG_DIM):
        raise NonRetryableError(
            f"Image dimensions out of range: {width}x{height}",
            reason_code=ReasonCode.FRAME_INVALID_MAGIC_BYTES,
            http_status=422,
        )
    return width, height


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

    # S01.5: indice nao-negativo (defesa em profundidade além do Header ge=0).
    started_at = time.perf_counter()
    if request.frame_index < 0:
        raise NonRetryableError(
            f"Invalid frame_index: {request.frame_index}",
            reason_code=ReasonCode.FRAME_INVALID_MAGIC_BYTES,
            http_status=422,
        )

    if request.page_number is not None and request.page_number < 0:
        raise NonRetryableError(
            f"Invalid page_number: {request.page_number}",
            reason_code=ReasonCode.FRAME_INVALID_MAGIC_BYTES,
            http_status=422,
        )
    if request.frame_number is not None and request.frame_number < 0:
        raise NonRetryableError(
            f"Invalid frame_number: {request.frame_number}",
            reason_code=ReasonCode.FRAME_INVALID_MAGIC_BYTES,
            http_status=422,
        )

    # Validate MIME, magic bytes e conteudo real decodificado (dimensoes do conteudo).
    _validate_mime(request.data, request.mime_type)

    # Validate size
    if len(request.data) > MAX_FRAME_SIZE:
        raise NonRetryableError(
            f"Frame too large: {len(request.data)} bytes",
            reason_code=ReasonCode.FRAME_TOO_LARGE,
            http_status=413,
        )
    decoded_w, decoded_h = _validate_image_content(request.data, request.mime_type)

    # Compute and verify SHA-256
    actual_sha256 = _compute_sha256(request.data)
    if actual_sha256.lower() != request.declared_sha256.lower():
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_HASH_MISMATCH,
            message=f"SHA-256 mismatch: declared={request.declared_sha256} actual={actual_sha256}",
        )

    # Check session exists
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

    # Resolve Capture — create if not exists with capture_source
    capture_source = request.capture_source
    if capture_source not in ("ANDROID_CAMERA", "ESP32_CAMERA"):
        capture_source = "ANDROID_CAMERA"
    requested_config = getattr(session_obj, "requested_camera_config_json", None) or {}
    effective_config = getattr(session_obj, "effective_camera_config_json", None) or {}
    technical_config = (
        effective_config.get("technical_config")
        or requested_config.get("technical_config")
        or {}
    )
    requested_resolution = requested_config.get("frame_size") or request.source_resolution
    effective_resolution = effective_config.get("frame_size") or requested_resolution
    requested_quality = requested_config.get("esp_jpeg_quality")
    effective_quality = effective_config.get("esp_jpeg_quality")
    expected_frames = requested_config.get("frame_count")
    configured_buffer = technical_config.get("buffer_bytes")
    dma_enabled = technical_config.get("dma_enabled")
    cap_result = await db_session.execute(
        select(Capture)
        .where(Capture.session_id == session_obj.id, Capture.capture_id == request.capture_id)
        .with_for_update()
    )
    capture_obj = cap_result.scalar_one_or_none()
    if capture_obj is None:
        # S02.7: captura nova só pode nascer em estado aberto; após fechamento,
        # nem capture novo nem frame novo são aceitos.
        if SessionState(session_obj.status) not in UPLOAD_OPEN_STATES:
            raise FrameConflictError(
                reason_code=ReasonCode.SESSION_LOCKED,
                message="Session is closed — new capture rejected",
            )
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
            camera_profile_revision_id=getattr(session_obj, "camera_profile_revision_id", None),
            camera_profile_snapshot_json=getattr(
                session_obj, "camera_profile_snapshot_json", None
            ),
            requested_camera_config_json=requested_config or None,
            effective_camera_config_json=effective_config or None,
            firmware_version=getattr(session_obj, "firmware_version", None),
            capabilities_version=getattr(session_obj, "capabilities_version", None),
            page_number=request.page_number,
            requested_resolution=requested_resolution,
            effective_resolution=effective_resolution,
            requested_esp_jpeg_quality=requested_quality,
            effective_esp_jpeg_quality=effective_quality,
            configured_buffer_bytes=configured_buffer,
            dma_enabled=dma_enabled,
            expected_frames=expected_frames,
        )
        db_session.add(capture_obj)
        await db_session.flush()

    # Idempotency PRIMEIRO (S02.7): duplicata idêntica de frame conhecido retorna
    # confirmação mesmo após fechamento; só frame NOVO é bloqueado.
    existing_result = await db_session.execute(
        select(Frame).where(
            Frame.capture_id == capture_obj.id,
            Frame.frame_index == request.frame_index,
        )
    )
    existing_frame = existing_result.scalar_one_or_none()
    if existing_frame is not None:
        if existing_frame.sha256.lower() == actual_sha256.lower():
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
                derived_storage_key=derived_key(
                    request.session_id, "ocr", f"{request.capture_id}-{request.frame_index}"
                ),
            )
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_DUPLICATE_CONFLICT,
            message=f"Frame index {request.frame_index} already exists with different sha256",
        )

    # Frame novo após fechamento → 409 (S02.7/A10). A10 exige LOCKED e
    # processamento posterior rejeitando inclusão tardia.
    if SessionState(session_obj.status) not in UPLOAD_OPEN_STATES:
        raise FrameConflictError(
            reason_code=ReasonCode.SESSION_LOCKED,
            message="Session is locked or terminal — frame rejected",
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
            derived_storage_key=derived_key(
                request.session_id, "ocr", f"{request.capture_id}-{request.frame_index}"
            ),
        )

    # Upload to storage (overwrite=False — never overwrite originals).
    # S02.3/A15: conciliação objeto-gravado/linha-ausente — se o objeto já existe
    # com o MESMO hash (falha anterior entre put e commit), revincula em vez de 409.
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
    except StorageError as exc:
        from src.pages_to_audio.common.errors import StorageOverwriteForbidden

        if not isinstance(exc, StorageOverwriteForbidden):
            logger.warning(
                "frame_storage_failed",
                session_id=request.session_id,
                capture_id=request.capture_id,
                frame_index=request.frame_index,
            )
            raise
        # Objeto imutável já existe: baixar e comparar hash.
        try:
            existing_bytes = await storage.get_object("pages-originals", storage_key)
        except StorageError:
            raise
        if _compute_sha256(existing_bytes).lower() != actual_sha256.lower():
            raise FrameConflictError(
                reason_code=ReasonCode.FRAME_DUPLICATE_CONFLICT,
                message="Storage object exists with different content — ORIGINAL immutable",
            ) from exc
        # Mesmo conteúdo: falha anterior foi após put e antes do commit.
        # Conclui o vínculo do mesmo objeto (idempotente).
        logger.warning(
            "frame_storage_reconciled",
            session_id=request.session_id,
            capture_id=request.capture_id,
            frame_index=request.frame_index,
        )

    # Insert Frame (dimensões derivadas do conteúdo decodificado, não do header).
    received_at = _parse_received_at(request.received_android_at)
    frame = Frame(
        session_id=session_obj.id,
        capture_id=capture_obj.id,
        frame_index=request.frame_index,
        sha256=actual_sha256,
        content_length=len(request.data),
        mime_type=request.mime_type,
        width=decoded_w,
        height=decoded_h,
        storage_key=storage_key,
        received_android_at=received_at,
        capture_source=capture_source,
        android_orientation=request.android_orientation,
        source_resolution=request.source_resolution,
        page_number=request.page_number,
        frame_number=(
            request.frame_number if request.frame_number is not None else request.frame_index
        ),
        requested_resolution=requested_resolution,
        effective_resolution=effective_resolution,
        requested_esp_jpeg_quality=requested_quality,
        effective_esp_jpeg_quality=effective_quality,
        configured_buffer_bytes=configured_buffer,
        dma_enabled=dma_enabled,
        firmware_version=getattr(session_obj, "firmware_version", None),
        jpeg_size_bytes=len(request.data),
        jpeg_valid=True,
        storage_key_original=storage_key,
        upload_duration_ms=round((time.perf_counter() - started_at) * 1000),
        confirmed_at=datetime.now(UTC),
        status="accepted",
    )
    db_session.add(frame)
    capture_obj.received_frames = int(capture_obj.received_frames or 0) + 1
    try:
        await db_session.flush()
    except Exception:
        # S02.3/§12.3: falha de DB após storage OK registra órfão para o job de
        # reconciliação (transação própria — sobrevive ao rollback do chamador).
        try:
            from src.pages_to_audio.capture.orphans import record_orphan

            await record_orphan(
                bucket="pages-originals",
                key=storage_key,
                sha256=actual_sha256,
                session_db_id=session_obj.id,
            )
        except Exception as orphan_exc:
            logger.warning(
                "frame_orphan_record_failed",
                error=str(orphan_exc)[:160],
                storage_key=storage_key,
            )
        raise
    await db_session.refresh(frame)

    derivative = await persist_ocr_derivative(
        storage=storage,
        db_session=db_session,
        session_id=request.session_id,
        session_db_id=session_obj.id,
        capture_id=request.capture_id,
        frame_index=request.frame_index,
        frame_id=frame.id,
        original_storage_key=storage_key,
        original_sha256=actual_sha256,
        original_bytes=request.data,
    )

    logger.info(
        "frame_uploaded",
        session_id=request.session_id,
        capture_id=request.capture_id,
        frame_index=request.frame_index,
        sha256=actual_sha256,
        storage_key=storage_key,
        frame_id=str(frame.id),
        derived_storage_key=derivative.storage_key,
    )
    return FrameUploadResult(
        frame_db_id=str(frame.id),
        storage_key=storage_key,
        sha256=actual_sha256,
        size_bytes=len(request.data),
        derived_storage_key=derivative.storage_key,
    )
