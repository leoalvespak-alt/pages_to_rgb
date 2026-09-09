"""D01/D02/D04 — namespace gateway do diagnóstico (extensão aditiva).

Reutiliza auth cloud (token + X-Gateway-Id), banco, storage e fila durável
conceitual do Android. ACKs distintos dos de missão: preview usa endpoint
transitório separado e nunca conta como foto salva.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from apps.api.dependencies import SettingsDep, UowDep
from src.pages_to_audio.auth.gateway import verify_gateway_token
from src.pages_to_audio.camera_diagnostics.service import (
    fail_diagnostic,
    ingest_frame,
    mark_active,
    stop_diagnostic,
)
from src.pages_to_audio.common.contract_ids import ESP_ID_PATTERN
from src.pages_to_audio.common.errors import AppError, FrameConflictError
from src.pages_to_audio.db.models.camera_diagnostic import CameraDiagnostic
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.observability.logging import get_logger
from src.pages_to_audio.storage import get_storage_adapter

logger = get_logger(__name__)

router = APIRouter(
    prefix="/gateway/diagnostics",
    tags=["gateway-diagnostics"],
    dependencies=[Depends(verify_gateway_token)],
)

GatewayIdDep = Annotated[str, Depends(verify_gateway_token)]


def _diag_bucket(settings: SettingsDep) -> str:
    if settings.CAMERA_DIAGNOSTICS_BUCKET:
        return settings.CAMERA_DIAGNOSTICS_BUCKET
    return settings.R2_BUCKET_ORIGINALS or settings.SUPABASE_BUCKET_ORIGINALS or "pages-originals"


async def _load(uow: UowDep, diagnostic_id: str) -> tuple[CameraDiagnostic, str]:
    row = await uow.session.scalar(
        select(CameraDiagnostic).where(CameraDiagnostic.diagnostic_id == diagnostic_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Diagnostic not found")
    device = await uow.session.get(Device, row.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return row, device.device_code


async def _require_binding(
    uow: UowDep, settings: SettingsDep, gateway_id: str, row: CameraDiagnostic
) -> str:
    """C01/RA25: cerca central — flag + vínculo gateway/device + lease."""
    if not settings.CAMERA_DIAGNOSTICS_ENABLED:
        raise HTTPException(status_code=403, detail="Diagnostics disabled")
    locked_row = await uow.session.scalar(
        select(CameraDiagnostic)
        .where(CameraDiagnostic.id == row.id)
        .with_for_update()
    )
    if locked_row is None:
        raise HTTPException(status_code=404, detail="Diagnostic not found")
    row = locked_row
    device = await uow.session.get(Device, row.device_id)
    if device is None or not device.enabled:
        raise HTTPException(status_code=404, detail="Device not found")
    gateway = await uow.session.scalar(
        select(AndroidGateway).where(AndroidGateway.gateway_code == gateway_id)
    )
    if gateway is None:
        raise HTTPException(status_code=403, detail="Unknown gateway")
    # Gateway reivindicado na claim, ou primeiro contato ainda sem dono.
    if row.gateway_id is not None and row.gateway_id != gateway.id:
        raise HTTPException(status_code=403, detail="Diagnostic owned by another gateway")
    if row.gateway_id is None:
        row.gateway_id = gateway.id
        await uow.session.flush()
    # Lease: expirados não operam (expiração validada em toda ingestão/evento).
    from src.pages_to_audio.camera_diagnostics.service import expire_stale

    await expire_stale(uow.session)
    await uow.session.refresh(row)
    if row.status in ("EXPIRED",):
        raise HTTPException(status_code=410, detail="Diagnostic expired")
    return device.device_code


@router.get("/pending")
async def pending(
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
    device_code: str = Query(..., min_length=1, max_length=63, pattern=ESP_ID_PATTERN),
) -> dict[str, Any]:
    """C01/C05 — entrega cloud→Android: pedidos REQUESTED não expirados do dispositivo."""
    if not settings.CAMERA_DIAGNOSTICS_ENABLED:
        raise HTTPException(status_code=403, detail="Diagnostics disabled")
    from datetime import UTC, datetime

    from src.pages_to_audio.camera_diagnostics.service import expire_stale

    await expire_stale(uow.session)
    device = await uow.session.scalar(
        select(Device).where(Device.device_code == device_code)
    )
    if device is None or not device.enabled:
        return {"device_code": device_code, "pending": []}
    rows = (
        await uow.session.scalars(
            select(CameraDiagnostic)
            .where(
                CameraDiagnostic.device_id == device.id,
                CameraDiagnostic.status == "REQUESTED",
                CameraDiagnostic.expires_at > datetime.now(UTC),
            )
            .order_by(CameraDiagnostic.created_at)
        )
    ).all()
    return {
        "device_code": device_code,
        "pending": [
            {
                "diagnostic_id": r.diagnostic_id,
                "mode": r.mode,
                "resolution": (r.requested_profile or {}).get("resolution", "SVGA"),
                "jpeg_quality": (r.requested_profile or {}).get("jpeg_quality", 18),
                "duration_s": r.duration_limit_s,
                "max_frames": r.max_frames,
            }
            for r in rows
        ],
    }


class ClaimRequest(BaseModel):
    capabilities: list[str] = Field(default_factory=list)


@router.post("/{diagnostic_id}/claim")
async def claim(
    diagnostic_id: str,
    body: ClaimRequest,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    row, _device_code = await _load(uow, diagnostic_id)
    await _require_binding(uow, settings, gateway_id, row)
    if "camera_diagnostics_v1" not in (body.capabilities or []):
        raise HTTPException(status_code=501, detail="Gateway without camera_diagnostics_v1")
    if row.status not in ("REQUESTED", "ACTIVE"):
        raise HTTPException(status_code=409, detail=f"Diagnostic is {row.status}")
    row = await mark_active(uow.session, row, gateway_id, effective=None)
    await uow.session.flush()
    return {"diagnostic_id": row.diagnostic_id, "status": row.status,
            "mode": row.mode, "limits": {"duration_limit_s": row.duration_limit_s,
            "bytes_limit": row.bytes_limit, "max_frames": row.max_frames}}


class DiagEvent(BaseModel):
    event: Literal["ACTIVE", "FRAME", "STOPPED", "FAILED"]
    frame_index: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, max_length=64)
    bytes: int | None = Field(default=None, ge=0)
    reason: str | None = Field(default=None, max_length=280)


@router.post("/{diagnostic_id}/event")
async def event(
    diagnostic_id: str,
    body: DiagEvent,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    row, _ = await _load(uow, diagnostic_id)
    await _require_binding(uow, settings, gateway_id, row)
    if body.event == "ACTIVE":
        row = await mark_active(uow.session, row, gateway_id, effective=None)
    elif body.event == "STOPPED":
        await stop_diagnostic(uow.session, row, body.reason or body.event.lower())
    elif body.event == "FAILED":
        await fail_diagnostic(uow.session, row, body.reason or body.event.lower())
    await uow.session.flush()
    return {"diagnostic_id": row.diagnostic_id, "status": row.status}


async def _read_limited(file: UploadFile, limit: int = 12 * 1024 * 1024) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(status_code=413, detail="Frame body exceeds size limit")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/{diagnostic_id}/frame", status_code=201)
async def upload_frame(
    diagnostic_id: str,
    file: UploadFile,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
    x_frame_index: int = Header(..., alias="X-Frame-Index", ge=0, le=10000),
    x_sha256: str = Header(..., alias="X-SHA256", min_length=64, max_length=64,
                           pattern=r"^[0-9a-fA-F]{64}$"),
    x_captured_mono_ms: int | None = Header(None, alias="X-Captured-Mono-Ms", ge=0),
    x_width: int | None = Header(None, alias="X-Width", ge=0),
    x_height: int | None = Header(None, alias="X-Height", ge=0),
) -> dict[str, Any]:
    """Foto/frame de clipe (durável). Prévia usa /preview (transitório)."""
    row, _ = await _load(uow, diagnostic_id)
    device_code = await _require_binding(uow, settings, gateway_id, row)
    data = await _read_limited(file)
    try:
        rec, dup = await ingest_frame(
            uow.session, get_storage_adapter(), _diag_bucket(settings),
            row=row, device_code=device_code, frame_index=x_frame_index,
            declared_sha256=x_sha256, data=data, width=x_width, height=x_height,
            captured_mono_ms=x_captured_mono_ms, transient=False,
        )
        await uow.session.flush()
    except (AppError, FrameConflictError, ValueError) as exc:
        raise HTTPException(
            status_code=getattr(exc, "http_status", 400), detail=str(exc)) from exc
    return {"diagnostic_id": row.diagnostic_id, "frame_index": rec.frame_index,
            "sha256": rec.sha256, "storage_key": rec.storage_key,
            "duplicate": dup, "status": 208 if dup else 201}


@router.post("/{diagnostic_id}/preview", status_code=201)
async def upload_preview(
    diagnostic_id: str,
    file: UploadFile,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
    x_frame_index: int = Header(..., alias="X-Frame-Index", ge=0, le=10000),
    x_sha256: str = Header(..., alias="X-SHA256", min_length=64, max_length=64,
                           pattern=r"^[0-9a-fA-F]{64}$"),
    x_captured_mono_ms: int | None = Header(None, alias="X-Captured-Mono-Ms", ge=0),
    x_width: int | None = Header(None, alias="X-Width", ge=0),
    x_height: int | None = Header(None, alias="X-Height", ge=0),
) -> dict[str, Any]:
    """ACK transitório de prévia (endpoint separado; sem garantia de foto)."""
    row, _ = await _load(uow, diagnostic_id)
    device_code = await _require_binding(uow, settings, gateway_id, row)
    if row.mode != "PREVIEW":
        raise HTTPException(status_code=409, detail="Not a PREVIEW diagnostic")
    data = await _read_limited(file)
    try:
        rec, dup = await ingest_frame(
            uow.session, get_storage_adapter(), _diag_bucket(settings),
            row=row, device_code=device_code, frame_index=x_frame_index,
            declared_sha256=x_sha256, data=data, width=x_width, height=x_height,
            captured_mono_ms=x_captured_mono_ms, transient=True,
        )
        await uow.session.flush()
    except (AppError, FrameConflictError, ValueError) as exc:
        raise HTTPException(
            status_code=getattr(exc, "http_status", 400), detail=str(exc)) from exc
    return {"diagnostic_id": row.diagnostic_id, "frame_index": rec.frame_index,
            "sha256": rec.sha256, "transient": True, "duplicate": dup}


@router.post("/{diagnostic_id}/ack")
async def ack(
    diagnostic_id: str,
    gateway_id: GatewayIdDep,
    uow: UowDep,
    settings: SettingsDep,
) -> dict[str, Any]:
    row, _ = await _load(uow, diagnostic_id)
    await _require_binding(uow, settings, gateway_id, row)
    if row.status == "STOPPING":
        row.status = "COMPLETED"
        from datetime import UTC, datetime

        row.completed_at = datetime.now(UTC)
        await uow.session.flush()
    return {"diagnostic_id": row.diagnostic_id, "status": row.status, "acked": True}
