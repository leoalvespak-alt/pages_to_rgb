"""D01/D04/D05 — API administrativa de diagnóstico de câmera.

Namespace próprio /api/v1/admin/camera-diagnostics (contrato
P2A-CAMERA-DIAG-2026-09-09 §4). Somente administradores, atrás da flag
CAMERA_DIAGNOSTICS_ENABLED. Nunca altera missão/spool/OCR/solver/RGB/áudio.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from apps.api.dependencies import SettingsDep, UowDep
from src.pages_to_audio.auth.admin import AdminClaimsDep, AdminCsrfDep
from src.pages_to_audio.camera_diagnostics import STALE_AFTER_S, is_diagnostic_key
from src.pages_to_audio.camera_diagnostics.service import (
    create_diagnostic,
    expire_stale,
    ingest_frame,
    retention_cleanup,
    stop_diagnostic,
)
from src.pages_to_audio.camera_diagnostics.video import convert_clip
from src.pages_to_audio.common.contract_ids import ESP_ID_PATTERN
from src.pages_to_audio.common.errors import AppError, FrameConflictError
from src.pages_to_audio.db.models.camera_diagnostic import (
    CameraDiagnostic,
    CameraDiagnosticFrame,
)
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.storage import get_storage_adapter

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/camera-diagnostics", tags=["admin-camera-diagnostics"])


def _diag_bucket(settings: SettingsDep) -> str:
    if settings.CAMERA_DIAGNOSTICS_BUCKET:
        return settings.CAMERA_DIAGNOSTICS_BUCKET
    return settings.R2_BUCKET_ORIGINALS or settings.SUPABASE_BUCKET_ORIGINALS or "pages-originals"


class DiagProfile(BaseModel):
    resolution: str = Field(default="SVGA", max_length=16)
    jpeg_quality: int = Field(default=18, ge=5, le=40)


class DiagCreate(BaseModel):
    device_code: str = Field(min_length=1, max_length=63, pattern=ESP_ID_PATTERN)
    mode: Literal["PHOTO", "CLIP", "PREVIEW"] = "PHOTO"
    profile: DiagProfile = Field(default_factory=DiagProfile)
    duration_s: int | None = Field(default=None, ge=1, le=60)
    note: str | None = Field(default=None, max_length=280)


class DiagState(BaseModel):
    diagnostic_id: str
    device_code: str
    gateway_code: str | None
    mode: str
    status: str
    requested_profile: dict[str, Any] | None
    effective_profile: dict[str, Any] | None
    origin: str
    created_at: datetime | None
    expires_at: datetime | None
    completed_at: datetime | None
    reason: str | None
    counters: dict[str, Any]


async def _load(db: UowDep, diagnostic_id: str) -> tuple[CameraDiagnostic, str, str | None]:
    row = await db.session.scalar(
        select(CameraDiagnostic).where(CameraDiagnostic.diagnostic_id == diagnostic_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Diagnostic not found")
    device = await db.session.get(Device, row.device_id)
    gateway_code: str | None = None
    if row.gateway_id is not None:
        gw = await db.session.get(AndroidGateway, row.gateway_id)
        gateway_code = gw.gateway_code if gw is not None else None
    return row, (device.device_code if device else "?"), gateway_code


def _to_state(
    row: CameraDiagnostic, device_code: str, gateway_code: str | None
) -> DiagState:
    return DiagState(
        diagnostic_id=row.diagnostic_id,
        device_code=device_code,
        gateway_code=gateway_code,
        mode=row.mode,
        status=row.status,
        requested_profile=row.requested_profile,
        effective_profile=row.effective_profile,
        origin=row.origin,
        created_at=row.created_at,
        expires_at=row.expires_at,
        completed_at=row.completed_at,
        reason=row.reason,
        counters={
            "received_frames": row.received_frames,
            "bytes": row.received_bytes,
            "last_frame_index": row.last_frame_index,
            "last_frame_at": row.last_frame_at.isoformat() if row.last_frame_at else None,
        },
    )


@router.post("", status_code=201)
async def create(
    body: DiagCreate,
    _claims: AdminCsrfDep,
    uow: UowDep,
    settings: SettingsDep,
    response: Response,
) -> DiagState:
    await expire_stale(uow.session)
    try:
        row = await create_diagnostic(
            uow.session,
            device_code=body.device_code,
            mode=body.mode,
            resolution=body.profile.resolution,
            jpeg_quality=body.profile.jpeg_quality,
            duration_s=body.duration_s,
            created_by="admin",
            enabled=bool(settings.CAMERA_DIAGNOSTICS_ENABLED),
        )
        await uow.session.flush()
    except AppError as exc:
        raise HTTPException(status_code=exc.http_status, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    response.headers["Cache-Control"] = "no-store"
    loaded, device_code, gateway_code = await _load(uow, row.diagnostic_id)
    return _to_state(loaded, device_code, gateway_code)


@router.get("/{diagnostic_id}")
async def get_state(
    diagnostic_id: str, _claims: AdminClaimsDep, uow: UowDep, response: Response
) -> DiagState:
    await expire_stale(uow.session)
    row, device_code, gateway_code = await _load(uow, diagnostic_id)
    response.headers["Cache-Control"] = "no-store"
    return _to_state(row, device_code, gateway_code)


@router.post("/{diagnostic_id}/stop")
async def stop(
    diagnostic_id: str,
    _claims: AdminCsrfDep,
    uow: UowDep,
    settings: SettingsDep,
    response: Response,
) -> dict[str, Any]:
    row, _, _ = await _load(uow, diagnostic_id)
    if row.status in ("COMPLETED", "FAILED", "EXPIRED"):
        return {"diagnostic_id": row.diagnostic_id, "status": row.status, "ack": True}
    await stop_diagnostic(uow.session, row, "admin-stop")
    # Se for clipe com frames, tenta conversão final (idempotente, best-effort).
    if row.mode == "CLIP":
        try:
            bucket = settings.CAMERA_DIAGNOSTICS_BUCKET or settings.R2_BUCKET_ORIGINALS
            device = await uow.session.get(Device, row.device_id)
            await convert_clip(
                uow.session, get_storage_adapter(), bucket or "pages-originals",
                row, device.device_code if device else "?",
            )
        except Exception as exc:
            logger.warning("clip_final_convert_failed", error=str(exc)[:160])
    await uow.session.flush()
    response.headers["Cache-Control"] = "no-store"
    response.status_code = 202
    return {"diagnostic_id": row.diagnostic_id, "status": row.status, "ack": False}


@router.get("/{diagnostic_id}/latest")
async def latest(
    diagnostic_id: str, _claims: AdminClaimsDep, uow: UowDep, response: Response
) -> dict[str, Any]:
    from src.pages_to_audio.camera_diagnostics import effective_fps

    row, _, _ = await _load(uow, diagnostic_id)
    response.headers["Cache-Control"] = "no-store"
    if row.last_frame_key is None:
        return {"diagnostic_id": row.diagnostic_id, "status": row.status, "frame": None}
    now = datetime.now(UTC)
    age_s = (now - row.last_frame_at).total_seconds() if row.last_frame_at else None
    elapsed = (now - row.created_at).total_seconds() if row.created_at else 0
    stale = age_s is not None and age_s > STALE_AFTER_S
    return {
        "diagnostic_id": row.diagnostic_id,
        "status": row.status,
        "frame": {
            "frame_index": row.last_frame_index,
            "sequence": row.last_sequence,
            "sha256": row.last_frame_sha256,
            "storage_key": row.last_frame_key,
            "age_s": round(age_s, 1) if age_s is not None else None,
            "stale": stale,
            "stale_message": "imagem desatualizada" if stale else None,
            "effective_fps": effective_fps(int(row.received_frames or 0), elapsed),
        },
    }


@router.get("/{diagnostic_id}/latest.jpg")
async def latest_image(
    diagnostic_id: str,
    _claims: AdminClaimsDep,
    uow: UowDep,
    settings: SettingsDep,
) -> Response:
    from fastapi.responses import Response as FastResponse

    row, _, _ = await _load(uow, diagnostic_id)
    if not row.last_frame_key or not is_diagnostic_key(row.last_frame_key):
        raise HTTPException(status_code=404, detail="No frame yet")
    bucket = (
        settings.CAMERA_DIAGNOSTICS_BUCKET
        or settings.R2_BUCKET_ORIGINALS
        or "pages-originals"
    )
    try:
        data = await get_storage_adapter().get_object(bucket, row.last_frame_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Storage unavailable") from exc
    return FastResponse(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


@router.get("/{diagnostic_id}/frames/{frame_index}.jpg")
async def frame_image(
    diagnostic_id: str,
    frame_index: int,
    _claims: AdminClaimsDep,
    uow: UowDep,
    settings: SettingsDep,
) -> Response:
    """Serve the immutable original for one gallery frame, never latest.jpg."""
    from fastapi.responses import Response as FastResponse

    row, _, _ = await _load(uow, diagnostic_id)
    frame = await uow.session.scalar(
        select(CameraDiagnosticFrame).where(
            CameraDiagnosticFrame.diagnostic_id == row.id,
            CameraDiagnosticFrame.frame_index == frame_index,
            CameraDiagnosticFrame.transient.is_(False),
        )
    )
    if frame is None or not is_diagnostic_key(frame.storage_key):
        raise HTTPException(status_code=404, detail="Frame not found")
    try:
        data = await get_storage_adapter().get_object(_diag_bucket(settings), frame.storage_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Storage unavailable") from exc
    return FastResponse(content=data, media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


@router.get("/{diagnostic_id}/clip.mp4")
async def clip_file(
    diagnostic_id: str,
    _claims: AdminClaimsDep,
    uow: UowDep,
    settings: SettingsDep,
) -> Response:
    """Serve the generated MP4 as a real media response (not a JSON anchor)."""
    from fastapi.responses import Response as FastResponse

    row, _, _ = await _load(uow, diagnostic_id)
    if not row.clip_key or not is_diagnostic_key(row.clip_key):
        raise HTTPException(status_code=404, detail="Clip not available")
    try:
        data = await get_storage_adapter().get_object(_diag_bucket(settings), row.clip_key)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Storage unavailable") from exc
    return FastResponse(content=data, media_type="video/mp4",
                        headers={"Cache-Control": "no-store", "Accept-Ranges": "bytes"})


@router.get("/{diagnostic_id}/assets")
async def assets(
    diagnostic_id: str,
    _claims: AdminClaimsDep,
    uow: UowDep,
    response: Response,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    row, _, _ = await _load(uow, diagnostic_id)
    total = (
        await uow.session.scalar(
            select(func.count())
            .select_from(CameraDiagnosticFrame)
            .where(CameraDiagnosticFrame.diagnostic_id == row.id)
        )
        or 0
    )
    frames = (
        await uow.session.scalars(
            select(CameraDiagnosticFrame)
            .where(CameraDiagnosticFrame.diagnostic_id == row.id)
            .order_by(CameraDiagnosticFrame.frame_index)
            .offset((page - 1) * limit)
            .limit(limit)
        )
    ).all()
    response.headers["Cache-Control"] = "no-store"
    photos = [
        {
            "frame_index": f.frame_index, "sha256": f.sha256, "bytes": f.bytes_,
            "width": f.width, "height": f.height, "storage_key": f.storage_key,
            "transient": f.transient,
        }
        for f in frames
        if not f.transient
    ]
    clips = (
        [{"mp4_key": row.clip_key, "duration_s": row.clip_duration_s, "fps": row.clip_fps}]
        if row.clip_key
        else []
    )
    return {
        "diagnostic_id": row.diagnostic_id, "mode": row.mode, "status": row.status,
        "photos": photos, "clips": clips, "page": page, "limit": limit,
        "total": total, "transient_latest_key": row.last_frame_key,
    }


@router.post("/{diagnostic_id}/frame", status_code=201)
async def upload_frame_admin_relay(
    diagnostic_id: str,
    file: UploadFile,
    _claims: AdminCsrfDep,
    uow: UowDep,
    settings: SettingsDep,
    x_frame_index: int = Header(..., alias="X-Frame-Index", ge=0, le=10000),
    x_sha256: str = Header(..., alias="X-SHA256", min_length=64, max_length=64,
                           pattern=r"^[0-9a-fA-F]{64}$"),
    x_captured_mono_ms: int | None = Header(None, alias="X-Captured-Mono-Ms", ge=0),
    x_width: int | None = Header(None, alias="X-Width", ge=0),
    x_height: int | None = Header(None, alias="X-Height", ge=0),
    x_transient: bool = Header(False, alias="X-Transient"),
) -> dict[str, Any]:
    """Relay administrativo (bancada): recebe JPEG direto quando gateway está
    em loopback de teste. Produção usa o namespace gateway (§5 do contrato)."""
    row, device_code, _ = await _load(uow, diagnostic_id)
    data = await file.read()
    if len(data) > 12 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Frame body exceeds size limit")
    try:
        rec, dup = await ingest_frame(
            uow.session, get_storage_adapter(), _diag_bucket(settings),
            row=row, device_code=device_code, frame_index=x_frame_index,
            declared_sha256=x_sha256, data=data, width=x_width, height=x_height,
            captured_mono_ms=x_captured_mono_ms, transient=bool(x_transient),
        )
        await uow.session.flush()
    except (AppError, FrameConflictError, ValueError) as exc:
        status = getattr(exc, "http_status", 400)
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    return {"diagnostic_id": row.diagnostic_id, "frame_index": rec.frame_index,
            "sha256": rec.sha256, "storage_key": rec.storage_key, "duplicate": dup}


@router.post("/{diagnostic_id}/cleanup")
async def cleanup(
    diagnostic_id: str, _claims: AdminCsrfDep, uow: UowDep, settings: SettingsDep,
) -> dict[str, Any]:
    from src.pages_to_audio.camera_diagnostics.service import cleanup_diagnostic_storage

    row, device_code, _ = await _load(uow, diagnostic_id)
    removed = await cleanup_diagnostic_storage(
        uow.session, get_storage_adapter(), _diag_bucket(settings),
        row=row, device_code=device_code,
    )
    await uow.session.flush()
    return {"diagnostic_id": row.diagnostic_id, "removed": removed}


@router.post("/maintenance/retention")
async def retention(
    _claims: AdminCsrfDep, uow: UowDep, settings: SettingsDep,
    device_code: str = Query(..., min_length=1, max_length=63, pattern=ESP_ID_PATTERN),
) -> dict[str, Any]:
    expired = await expire_stale(uow.session)
    stats = await retention_cleanup(
        uow.session, get_storage_adapter(), _diag_bucket(settings), device_code=device_code
    )
    await uow.session.flush()
    return {"expired": expired, **stats}
