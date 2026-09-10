"""Persistence and compatibility rules for immutable camera revisions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.camera_profiles.contract import (
    AVAILABLE_CAMERA_VALUES,
    PROTECTED_CAMERA_VALUES,
    UNAVAILABLE_CAMERA_CONTROLS,
    CameraMode,
    default_profile_values,
    normalize_camera_mode,
)
from src.pages_to_audio.config.settings import AppSettings
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.camera_profile_revision import CameraProfileRevision
from src.pages_to_audio.db.models.device import Device


class CameraProfileError(Exception):
    """Expected API error raised by the camera profile boundary."""

    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def device_supports_v2(device: Device | None, advertised_version: str | None = None) -> bool:
    if advertised_version == "v2":
        return True
    metadata = (device.metadata_ or {}) if device is not None else {}
    return any(
        metadata.get(key) == "v2" for key in ("camera_capabilities_version", "capabilities_version")
    )


def capabilities_payload(
    device: Device | None,
    settings: AppSettings,
    *,
    advertised_version: str | None = None,
) -> dict[str, Any]:
    metadata = (device.metadata_ or {}) if device is not None else {}
    firmware = (
        (device.firmware_version if device is not None else None)
        or metadata.get("firmware_version")
        or "unknown"
    )
    driver = str(metadata.get("driver_version") or "esp32-camera 2.1.7")
    compatible = device_supports_v2(device, advertised_version)
    enabled = bool(settings.CAMERA_CONTRACT_V2_ENABLED)
    reason_code: str | None = None
    if not enabled:
        reason_code = "CAMERA_CONTRACT_V2_DISABLED"
        message = (
            "Contrato de câmera v2 desativado até Android e firmware Production serem instalados."
        )
    elif not compatible:
        reason_code = "FIRMWARE_CAPABILITY_V2_REQUIRED"
        message = "Firmware sem capability v2; sessão de produção não pode usar perfis de câmera."
    else:
        message = (
            "Contrato de câmera v2 compatível; valores protegidos serão aplicados pela firmware."
        )
    return {
        "firmware_version": str(firmware),
        "driver_version": driver,
        "available": AVAILABLE_CAMERA_VALUES,
        "protected": PROTECTED_CAMERA_VALUES,
        "unavailable": UNAVAILABLE_CAMERA_CONTROLS,
        "feature_enabled": enabled and compatible,
        "compatible": compatible,
        "reason_code": reason_code,
        "message": message,
    }


def require_v2_enabled(
    settings: AppSettings,
    device: Device | None,
    *,
    advertised_version: str | None = None,
) -> None:
    if not settings.CAMERA_CONTRACT_V2_ENABLED:
        raise CameraProfileError(
            "Camera contract v2 is disabled until Android and Production firmware are installed",
            reason_code="CAMERA_CONTRACT_V2_DISABLED",
        )
    if not device_supports_v2(device, advertised_version):
        raise CameraProfileError(
            "Device firmware did not advertise camera capability v2",
            reason_code="FIRMWARE_CAPABILITY_V2_REQUIRED",
        )


def requested_profile_values(body: Any, mode: CameraMode) -> dict[str, Any]:
    values = body.model_dump(exclude={"device_code", "mode"}, exclude_none=True)
    defaults = default_profile_values(mode)
    if values.get("frame_count") is None:
        values["frame_count"] = defaults["frame_count"]
    return {**defaults, **values}


def profile_payload(row: CameraProfileRevision) -> dict[str, Any]:
    values = {
        "frame_size": row.frame_size,
        "esp_jpeg_quality": row.esp_jpeg_quality,
        "frame_count": row.frame_count,
        "intra_frame_gap_ms": row.intra_frame_gap_ms,
        "page_interval_ms": row.page_interval_ms,
        "brightness": row.brightness,
        "contrast": row.contrast,
        "saturation": row.saturation,
        "awb": row.awb,
        "awb_gain": row.awb_gain,
        "wb_mode": row.wb_mode,
        "aec": row.aec,
        "aec2": row.aec2,
        "agc": row.agc,
        "bpc": row.bpc,
        "wpc": row.wpc,
        "raw_gamma": row.raw_gamma,
        "lens_correction": row.lens_correction,
        "dcw": row.dcw,
        "hmirror": row.hmirror,
        "vflip": row.vflip,
        "special_effect": row.special_effect,
        "colorbar": row.colorbar,
        "technical_config": row.technical_config_json,
    }
    return values


async def _lock_scope(session: AsyncSession, mode: CameraMode, device_id: Any) -> None:
    """Serialize revision allocation, including the empty-scope first insert."""

    bind = session.bind
    if bind is not None and getattr(getattr(bind, "dialect", None), "name", None) == "postgresql":
        scope = f"camera-profile:{device_id or 'global'}:{mode.value}"
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:scope))"), {"scope": scope}
        )


async def find_device(session: AsyncSession, device_code: str | None) -> Device | None:
    if not device_code:
        return None
    return await session.scalar(select(Device).where(Device.device_code == device_code))


async def active_profile(
    session: AsyncSession, *, mode: CameraMode, device_id: Any = None
) -> CameraProfileRevision | None:
    return await session.scalar(
        select(CameraProfileRevision)
        .where(
            CameraProfileRevision.mode == mode.value,
            CameraProfileRevision.device_id == device_id,
            CameraProfileRevision.active.is_(True),
        )
        .order_by(desc(CameraProfileRevision.revision))
    )


async def create_profile(
    session: AsyncSession,
    body: Any,
    *,
    actor: str,
    settings: AppSettings,
    require_feature: bool = True,
) -> CameraProfileRevision:
    mode = normalize_camera_mode(body.mode)
    if require_feature and not settings.CAMERA_CONTRACT_V2_ENABLED:
        raise CameraProfileError(
            "Camera contract v2 is disabled until Android and Production firmware are installed",
            reason_code="CAMERA_CONTRACT_V2_DISABLED",
        )
    device = await find_device(session, body.device_code)
    if body.device_code and device is None:
        raise CameraProfileError(
            "Device not found",
            reason_code="DEVICE_NOT_FOUND",
            status_code=404,
        )
    device_id = device.id if device is not None else None
    await _lock_scope(session, mode, device_id)
    latest = await session.scalar(
        select(CameraProfileRevision)
        .where(
            CameraProfileRevision.mode == mode.value,
            CameraProfileRevision.device_id == device_id,
        )
        .order_by(desc(CameraProfileRevision.revision))
        .with_for_update()
    )
    revision = int(latest.revision) + 1 if latest is not None else 1
    if latest is not None and latest.active:
        latest.active = False
        latest.superseded_at = datetime.now(UTC)
    values = requested_profile_values(body, mode)
    row = CameraProfileRevision(
        device_id=device_id,
        mode=mode.value,
        revision=revision,
        frame_size=values["frame_size"],
        esp_jpeg_quality=values["esp_jpeg_quality"],
        frame_count=values["frame_count"],
        intra_frame_gap_ms=values["intra_frame_gap_ms"],
        page_interval_ms=values["page_interval_ms"],
        brightness=values["brightness"],
        contrast=values["contrast"],
        saturation=values["saturation"],
        awb=values["awb"],
        awb_gain=values["awb_gain"],
        wb_mode=values["wb_mode"],
        aec=values["aec"],
        aec2=values["aec2"],
        agc=values["agc"],
        bpc=values["bpc"],
        wpc=values["wpc"],
        raw_gamma=values["raw_gamma"],
        lens_correction=values["lens_correction"],
        dcw=values["dcw"],
        hmirror=values["hmirror"],
        vflip=values["vflip"],
        special_effect=values["special_effect"],
        colorbar=values["colorbar"],
        technical_config_json=values["technical_config"],
        capabilities_version="v2",
        created_by=actor,
    )
    session.add(row)
    await session.flush()
    session.add(
        AuditEvent(
            event_type="CAMERA_PROFILE_CREATED",
            stage="CONFIG",
            severity="INFO",
            reason_code=None,
            actor_type="admin" if actor == "admin" else "gateway",
            payload={
                "profile_public_id": str(row.public_id),
                "mode": mode.value,
                "revision": revision,
                "device_code": body.device_code,
                "capabilities_version": "v2",
            },
        )
    )
    return row


async def ensure_default_profile(
    session: AsyncSession,
    *,
    mode: CameraMode,
    actor: str,
    settings: AppSettings,
) -> CameraProfileRevision:
    current = await active_profile(session, mode=mode)
    if current is not None:
        return current

    class DefaultProfileRequest:
        device_code = None

        def __init__(self, profile_mode: CameraMode) -> None:
            self.mode = profile_mode.value

        def model_dump(self, **_: Any) -> dict[str, Any]:
            return default_profile_values(self.mode)

    return await create_profile(
        session,
        DefaultProfileRequest(mode),
        actor=actor,
        settings=settings,
        require_feature=True,
    )


def revision_read_payload(row: CameraProfileRevision, device_code: str | None) -> dict[str, Any]:
    payload = profile_payload(row)
    return {
        "public_id": str(row.public_id),
        "device_code": device_code,
        "mode": row.mode,
        "revision": row.revision,
        "capabilities_version": row.capabilities_version,
        "requested": payload,
        "effective": payload,
        "created_by": row.created_by,
        "created_at": row.created_at,
        "active": row.active,
    }
