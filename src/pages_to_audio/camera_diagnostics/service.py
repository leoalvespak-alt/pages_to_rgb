"""D01/D04/D05 — serviço de diagnóstico: ingestão, estado, quotas, limpeza, vídeo.

Reutiliza transporte autenticado, banco, storage e worker existentes.
Nunca toca contratos de missão, spool principal, OCR/solver/RGB/áudio.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.camera_diagnostics import (
    AUTHZ_TTL_S,
    HISTORY_DAYS,
    HISTORY_MAX_BYTES_PER_DEVICE,
    PREVIEW_TRANSIENT_TTL_S,
    TERMINAL_STATUSES,
    VALID_MODES,
    diag_prefix,
    is_diagnostic_key,
    limits_for_mode,
    validate_profile,
)
from src.pages_to_audio.camera_diagnostics.video import schedule_clip_conversion
from src.pages_to_audio.capture.frame_upload import (
    _compute_sha256,
    _validate_image_content,
    _validate_mime,
)
from src.pages_to_audio.common.contract_ids import is_valid_esp_id
from src.pages_to_audio.common.errors import (
    FrameConflictError,
    NonRetryableError,
    ReasonCode,
    StorageError,
)
from src.pages_to_audio.db.models.camera_diagnostic import (
    CameraDiagnostic,
    CameraDiagnosticFrame,
)
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.domain.ports.storage import StoragePort
from src.pages_to_audio.observability.logging import get_logger

logger = get_logger(__name__)

CAPABILITY = "camera_diagnostics_v1"

# Exclusão atômica por dispositivo (processo único; com múltiplos workers a
# trava real é SELECT ... FOR UPDATE na linha ACTIVE — ver _assert_exclusive).
_active_lock: dict[str, str] = {}


def new_diagnostic_id() -> str:
    return "dg_" + secrets.token_hex(8)


async def _device_by_code(db: AsyncSession, device_code: str) -> Device | None:
    return await db.scalar(select(Device).where(Device.device_code == device_code))


async def _assert_exclusive(db: AsyncSession, device_id: object, new_diag_id: str) -> None:
    """Uma aquisição por vez, inclusive contra missão ativa (contrato §1)."""
    await db.scalar(select(Device).where(Device.id == device_id).with_for_update())
    active = await db.scalar(
        select(CameraDiagnostic)
        .where(
            CameraDiagnostic.device_id == device_id,  # type: ignore[arg-type]
            CameraDiagnostic.status.in_(["REQUESTED", "ACTIVE", "STOPPING"]),
        )
        .with_for_update()
    )
    if active is not None:
        raise NonRetryableError(
            "Device already has an active diagnostic",
            reason_code=ReasonCode.INVALID_REQUEST,
            http_status=409,
        )
    # Missão ativa/pausada ou RGB pendente negam diagnóstico sem alterar sessão.
    # Checagem: qualquer sessão CAPTURING/CAPTURE_* não-terminal do dispositivo.
    open_session = await db.scalar(
        select(Session)
        .where(
            Session.device_id == device_id,  # type: ignore[arg-type]
            Session.status.notin_(
                ["COMPLETED", "FAILED", "FAILED_RECOVERABLE", "CANCELLED", "LOCKED"]
            ),
        )
        .limit(1)
    )
    if open_session is not None:
        raise NonRetryableError(
            "Camera busy with mission session",
            reason_code=ReasonCode.SESSION_LOCKED,
            http_status=409,
        )


async def create_diagnostic(
    db: AsyncSession,
    *,
    device_code: str,
    mode: str,
    resolution: str | None,
    jpeg_quality: int | None,
    duration_s: int | None,
    created_by: str | None,
    enabled: bool,
) -> CameraDiagnostic:
    if not enabled:
        raise NonRetryableError(
            "Camera diagnostics disabled by feature flag",
            reason_code=ReasonCode.FORBIDDEN,
            http_status=403,
        )
    if mode not in VALID_MODES:
        raise NonRetryableError(
            "Invalid mode", reason_code=ReasonCode.INVALID_REQUEST, http_status=400
        )
    if not is_valid_esp_id(device_code):
        raise NonRetryableError(
            "Invalid device_code", reason_code=ReasonCode.INVALID_REQUEST, http_status=400
        )
    profile = validate_profile(resolution, jpeg_quality)
    limits = limits_for_mode(mode)
    dur = int(duration_s) if duration_s else int(limits["duration_limit_s"])
    if mode == "CLIP":
        from src.pages_to_audio.camera_diagnostics import CLIP_MAX_SECONDS

        if not 1 <= dur <= CLIP_MAX_SECONDS:
            raise NonRetryableError(
                "duration out of range", reason_code=ReasonCode.INVALID_REQUEST, http_status=400
            )
    elif mode == "PREVIEW":
        if not 1 <= dur <= 60:
            raise NonRetryableError(
                "duration out of range", reason_code=ReasonCode.INVALID_REQUEST, http_status=400
            )
    device = await _device_by_code(db, device_code)
    if device is None:
        raise NonRetryableError(
            "Device not found", reason_code=ReasonCode.NOT_FOUND, http_status=404
        )
    if not device.enabled:
        raise NonRetryableError(
            "Device disabled", reason_code=ReasonCode.DEVICE_DISABLED, http_status=403
        )
    diag_id = new_diagnostic_id()
    await _assert_exclusive(db, device.id, diag_id)
    now = datetime.now(UTC)
    row = CameraDiagnostic(
        diagnostic_id=diag_id,
        device_id=device.id,
        gateway_id=None,
        mode=mode,
        status="REQUESTED",
        requested_profile=dict(profile),
        effective_profile=None,
        origin="ESP32_CAMERA",
        duration_limit_s=dur,
        bytes_limit=int(limits["bytes_limit"]),
        max_frames=int(limits["max_frames"]),
        expires_at=now + timedelta(seconds=dur + AUTHZ_TTL_S),
        created_by=created_by,
    )
    db.add(row)
    await db.flush()
    logger.info("camera_diag_created", diagnostic_id=diag_id, mode=mode, device=device_code)
    return row


async def mark_active(
    db: AsyncSession, row: CameraDiagnostic, gateway_code: str, effective: dict | None
) -> CameraDiagnostic:
    locked_row = await db.scalar(
        select(CameraDiagnostic)
        .where(CameraDiagnostic.id == row.id)
        .with_for_update()
    )
    if locked_row is None:
        raise NonRetryableError(
            "Diagnostic not found", reason_code=ReasonCode.NOT_FOUND, http_status=404
        )
    row = locked_row
    if row.status not in ("REQUESTED", "ACTIVE"):
        raise NonRetryableError(
            f"Diagnostic is {row.status}",
            reason_code=ReasonCode.CAMERA_DIAG_NOT_ACTIVE,
            http_status=409,
        )
    gateway = await db.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_code)
    )
    if gateway is not None:
        row.gateway_id = gateway.id
    row.status = "ACTIVE"
    if effective:
        row.effective_profile = dict(effective)
    elif row.effective_profile is None:
        row.effective_profile = dict(row.requested_profile or {})
    await db.flush()
    return row


async def stop_diagnostic(db: AsyncSession, row: CameraDiagnostic, reason: str) -> CameraDiagnostic:
    if row.status in TERMINAL_STATUSES:
        return row
    row.status = "STOPPING"
    row.reason = reason
    await db.flush()
    # ACK de STOP confirma liberação: aqui o servidor marca COMPLETED quando
    # não há frames pendentes; gateway confirma via /ack (idempotente).
    return row


async def fail_diagnostic(
    db: AsyncSession, row: CameraDiagnostic, reason: str
) -> CameraDiagnostic:
    if row.status in TERMINAL_STATUSES:
        return row
    row.status = "FAILED"
    row.reason = reason
    row.completed_at = datetime.now(UTC)
    await db.flush()
    return row


async def ingest_frame(
    db: AsyncSession,
    storage: StoragePort,
    bucket: str,
    *,
    row: CameraDiagnostic,
    device_code: str,
    frame_index: int,
    declared_sha256: str,
    data: bytes,
    width: int | None,
    height: int | None,
    captured_mono_ms: int | None,
    transient: bool,
) -> tuple[CameraDiagnosticFrame, bool]:
    """Ingere JPEG com limite antes de leitura integral (chamador já limitou).

    Retorna (linha, duplicate). Idempotente por (diagnostic, índice, sha).
    Conflito de hash no mesmo índice → 409. Quota → 413.
    """
    locked_row = await db.scalar(
        select(CameraDiagnostic)
        .where(CameraDiagnostic.id == row.id)
        .with_for_update()
    )
    if locked_row is None:
        raise NonRetryableError(
            "Diagnostic not found", reason_code=ReasonCode.NOT_FOUND, http_status=404
        )
    row = locked_row
    if row.status not in ("REQUESTED", "ACTIVE"):
        raise FrameConflictError(
            reason_code=ReasonCode.SESSION_LOCKED, message="Diagnostic is not accepting frames"
        )
    # Validate identity and detect idempotent retransmission before charging a
    # quota.  A retry of an already accepted frame must remain 208 even when
    # the diagnostic has since reached its byte/frame ceiling.
    _validate_mime(data, "image/jpeg")
    decoded = _validate_image_content(data, "image/jpeg")
    actual = _compute_sha256(data)
    if actual.lower() != declared_sha256.lower():
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_HASH_MISMATCH,
            message="SHA-256 mismatch",
        )
    same_idx = (
        await db.scalars(
            select(CameraDiagnosticFrame).where(
                CameraDiagnosticFrame.diagnostic_id == row.id,
                CameraDiagnosticFrame.frame_index == frame_index,
            )
        )
    ).all()
    for f in same_idx:
        if f.sha256.lower() == actual.lower():
            return f, True
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_DUPLICATE_CONFLICT,
            message=f"Frame index {frame_index} exists with different hash",
        )
    if frame_index < 0 or frame_index >= 10000:
        raise NonRetryableError(
            "Invalid frame_index", reason_code=ReasonCode.INVALID_REQUEST, http_status=422
        )
    if len(data) > row.bytes_limit:
        raise NonRetryableError(
            "Frame exceeds diagnostic byte limit",
            reason_code=ReasonCode.FRAME_TOO_LARGE,
            http_status=413,
        )
    if int(row.received_bytes or 0) + len(data) > int(row.bytes_limit or 0):
        raise NonRetryableError(
            "Diagnostic byte quota exceeded",
            reason_code=ReasonCode.FRAME_TOO_LARGE,
            http_status=413,
        )
    if int(row.received_frames or 0) >= int(row.max_frames or 1) and not transient:
        # Prévia transitória reutiliza índice único; fotos/clipes respeitam teto.
        existing_count = await db.scalar(
            select(func.count())
            .select_from(CameraDiagnosticFrame)
            .where(CameraDiagnosticFrame.diagnostic_id == row.id)
        )
        if int(existing_count or 0) >= int(row.max_frames or 1):
            raise NonRetryableError(
                "Diagnostic frame quota exceeded",
                reason_code=ReasonCode.FRAME_TOO_LARGE,
                http_status=413,
            )
    _validate_mime(data, "image/jpeg")
    decoded = _validate_image_content(data, "image/jpeg")
    actual = _compute_sha256(data)
    if actual.lower() != declared_sha256.lower():
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_HASH_MISMATCH,
            message="SHA-256 mismatch",
        )
    same_idx = (
        await db.scalars(
            select(CameraDiagnosticFrame).where(
                CameraDiagnosticFrame.diagnostic_id == row.id,
                CameraDiagnosticFrame.frame_index == frame_index,
            )
        )
    ).all()
    for f in same_idx:
        if f.sha256.lower() == actual.lower():
            return f, True
        raise FrameConflictError(
            reason_code=ReasonCode.FRAME_DUPLICATE_CONFLICT,
            message=f"Frame index {frame_index} exists with different hash",
        )
    from src.pages_to_audio.camera_diagnostics import clip_frame_key, photo_key, preview_key

    if transient:
        key = preview_key(device_code, row.diagnostic_id)
    elif row.mode == "CLIP":
        key = clip_frame_key(device_code, row.diagnostic_id, frame_index)
    else:
        key = photo_key(device_code, row.diagnostic_id, frame_index)
    try:
        await storage.put_object(
            bucket, key, data, "image/jpeg", sha256=actual, overwrite=transient
        )
    except StorageError as exc:
        from src.pages_to_audio.common.errors import StorageOverwriteForbidden

        if isinstance(exc, StorageOverwriteForbidden):
            existing = await storage.get_object(bucket, key)
            if hashlib.sha256(existing).hexdigest().lower() != actual.lower():
                raise FrameConflictError(
                    reason_code=ReasonCode.FRAME_DUPLICATE_CONFLICT,
                    message="Storage object immutable with different content",
                ) from exc
        else:
            raise
    now = datetime.now(UTC)
    rec = CameraDiagnosticFrame(
        diagnostic_id=row.id,
        frame_index=frame_index,
        sequence=int(row.last_sequence or 0) + 1,
        sha256=actual,
        storage_key=key,
        bytes_=len(data),
        # Persist dimensions decoded from the JPEG.  Header declarations are
        # advisory and must not be allowed to falsify the stored geometry.
        width=decoded[0],
        height=decoded[1],
        captured_mono_ms=captured_mono_ms,
        received_at=now,
        transient=transient,
    )
    db.add(rec)
    row.received_frames = int(row.received_frames or 0) + 1
    row.received_bytes = int(row.received_bytes or 0) + len(data)
    # Ponteiro só avança (prévia): chegada atrasada não retrocede.
    if int(rec.sequence) >= int(row.last_sequence or 0):
        row.last_sequence = int(rec.sequence)
        row.last_frame_index = frame_index
        row.last_frame_sha256 = actual
        row.last_frame_key = key
        row.last_frame_at = now
    await db.flush()
    if row.mode == "CLIP" and not transient:
        # Agenda conversão quando o clipe atinge o esperado; idempotente.
        try:
            await schedule_clip_conversion(db, storage, bucket, row, device_code)
        except Exception as exc:
            logger.warning("clip_schedule_failed", error=str(exc)[:160])
    return rec, False


async def cleanup_diagnostic_storage(
    db: AsyncSession, storage: StoragePort, bucket: str, *, row: CameraDiagnostic, device_code: str
) -> int:
    """Expurga apenas chaves de diagnóstico verificadas. Retorna removidos."""
    prefix = diag_prefix(device_code, row.diagnostic_id)
    frames = (
        await db.scalars(
            select(CameraDiagnosticFrame).where(CameraDiagnosticFrame.diagnostic_id == row.id)
        )
    ).all()
    removed = 0
    for f in frames:
        key = f.storage_key
        if not key.startswith(prefix) or not is_diagnostic_key(key):
            continue
        if f.transient and key == row.last_frame_key:
            # Não remove o frame apontado enquanto válido.
            continue
        try:
            await storage.delete_object(bucket, key)
            removed += 1
        except Exception as exc:
            logger.warning("diag_cleanup_failed", key=key, error=str(exc)[:120])
    return removed


async def expire_stale(db: AsyncSession) -> int:
    now = datetime.now(UTC)
    rows = (
        await db.scalars(
            select(CameraDiagnostic).where(
                CameraDiagnostic.status.in_(["REQUESTED", "ACTIVE", "STOPPING"]),
                CameraDiagnostic.expires_at < now,
            )
        )
    ).all()
    for r in rows:
        r.status = "EXPIRED"
        r.reason = r.reason or "expired"
        r.completed_at = now
    await db.flush()
    return len(rows)


async def retention_cleanup(
    db: AsyncSession, storage: StoragePort, bucket: str, *, device_code: str
) -> dict[str, int]:
    """Histórico 7 d / 100 MiB por dispositivo; prévia transitória 10 min."""
    now = datetime.now(UTC)
    cutoff = now - timedelta(days=HISTORY_DAYS)
    old = (
        await db.scalars(
            select(CameraDiagnostic)
            .join(Device, CameraDiagnostic.device_id == Device.id)
            .where(
                Device.device_code == device_code,
                CameraDiagnostic.created_at < cutoff,
                CameraDiagnostic.status.in_(TERMINAL_STATUSES),
            )
        )
    ).all()
    removed_diags = 0
    removed_objs = 0
    for r in old:
        removed_objs += await cleanup_diagnostic_storage(
            db, storage, bucket, row=r, device_code=device_code
        )
        # The cleanup helper preserves the current transient pointer.  A
        # diagnostic older than the history window is no longer live, so remove
        # that final object and its metadata as well; otherwise assets would
        # reference deleted objects and the quota loop could revisit the row.
        if r.mode == "PREVIEW" and r.last_frame_key and is_diagnostic_key(r.last_frame_key):
            try:
                await storage.delete_object(bucket, r.last_frame_key)
                removed_objs += 1
            except Exception as exc:
                logger.warning("diag_cleanup_latest_failed", error=str(exc)[:120])
        frames = (
            await db.scalars(
                select(CameraDiagnosticFrame).where(CameraDiagnosticFrame.diagnostic_id == r.id)
            )
        ).all()
        for frame in frames:
            await db.delete(frame)
        await db.delete(r)
        removed_diags += 1
    # Prévia transitória antiga (>10 min) sem ser o ponteiro atual.
    transient_cutoff = now - timedelta(seconds=PREVIEW_TRANSIENT_TTL_S)
    transients = (
        await db.scalars(
            select(CameraDiagnosticFrame).where(
                CameraDiagnosticFrame.transient.is_(True),
                CameraDiagnosticFrame.received_at < transient_cutoff,
            )
        )
    ).all()
    for f in transients:
        diag = await db.get(CameraDiagnostic, f.diagnostic_id)
        if diag is not None and f.storage_key == diag.last_frame_key:
            continue
        if not is_diagnostic_key(f.storage_key):
            continue
        try:
            await storage.delete_object(bucket, f.storage_key)
            removed_objs += 1
            await db.delete(f)
        except Exception as exc:
            logger.warning("transient_cleanup_failed", error=str(exc)[:120])
    # Teto 100 MiB: remove diagnósticos mais antigos primeiro (só diagnóstico).
    device = await _device_by_code(db, device_code)
    total = 0
    if device is not None:
        total = (
            await db.scalar(
                select(func.coalesce(func.sum(CameraDiagnostic.received_bytes), 0)).where(
                    CameraDiagnostic.device_id == device.id
                )
            )
            or 0
        )
    while int(total or 0) > HISTORY_MAX_BYTES_PER_DEVICE:
        oldest = await db.scalar(
            select(CameraDiagnostic)
            .where(
                CameraDiagnostic.device_id == device.id,  # type: ignore[union-attr]
                CameraDiagnostic.received_bytes > 0,
                CameraDiagnostic.status.in_(TERMINAL_STATUSES),
            )
            .order_by(CameraDiagnostic.created_at)
            .limit(1)
        )
        if oldest is None:
            break
        removed_objs += await cleanup_diagnostic_storage(
            db, storage, bucket, row=oldest, device_code=device_code
        )
        total = int(total) - int(oldest.received_bytes or 0)
        removed_diags += 1
        # Mantém a linha (histórico) mas zera contadores? Não: remove só objetos.
        frames = (
            await db.scalars(
                select(CameraDiagnosticFrame).where(
                    CameraDiagnosticFrame.diagnostic_id == oldest.id
                )
            )
        ).all()
        for frame in frames:
            await db.delete(frame)
        await db.delete(oldest)
    await db.flush()
    return {"diagnostics": removed_diags, "objects": removed_objs}
