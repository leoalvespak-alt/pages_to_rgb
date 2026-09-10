"""S01 camera capabilities and immutable OCR/PHOTO profile revisions."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select

from apps.api.dependencies import SettingsDep, UowDep
from apps.api.schemas.admin import (
    CameraCapabilitiesV1,
    CameraProfileCreate,
    CameraProfileListResponse,
    CameraProfileRevisionRead,
)
from src.pages_to_audio.auth.admin import AdminClaimsDep, AdminCsrfDep
from src.pages_to_audio.auth.gateway import verify_gateway_token
from src.pages_to_audio.camera_profiles.service import (
    CameraProfileError,
    capabilities_payload,
    create_profile,
    find_device,
    revision_read_payload,
)
from src.pages_to_audio.db.models.camera_profile_revision import CameraProfileRevision

admin_router = APIRouter(prefix="/admin/camera-profiles", tags=["admin-camera-profiles"])
gateway_router = APIRouter(
    prefix="/gateway/camera",
    tags=["gateway-camera"],
    dependencies=[Depends(verify_gateway_token)],
)
GatewayIdDep = Annotated[str, Depends(verify_gateway_token)]


def _error(exc: CameraProfileError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"reason_code": exc.reason_code, "message": str(exc)},
    )


async def _capabilities(
    device_code: str,
    settings: SettingsDep,
    uow: UowDep,
    advertised_version: str | None = None,
) -> CameraCapabilitiesV1:
    device = await find_device(uow.session, device_code)
    return CameraCapabilitiesV1(
        **capabilities_payload(device, settings, advertised_version=advertised_version)
    )


@admin_router.get("/capabilities", response_model=CameraCapabilitiesV1)
async def admin_capabilities(
    _claims: AdminClaimsDep,
    settings: SettingsDep,
    uow: UowDep,
    device_code: str = Query(default="CAM-001", min_length=1, max_length=63),
) -> CameraCapabilitiesV1:
    return await _capabilities(device_code, settings, uow)


@admin_router.get("", response_model=CameraProfileListResponse)
async def list_profiles(
    _claims: AdminClaimsDep,
    settings: SettingsDep,
    uow: UowDep,
    device_code: str | None = Query(default=None, max_length=63),
) -> CameraProfileListResponse:
    device = await find_device(uow.session, device_code)
    device_id = device.id if device is not None else None
    rows = (
        await uow.session.scalars(
            select(CameraProfileRevision)
            .where(CameraProfileRevision.device_id == device_id)
            .order_by(CameraProfileRevision.mode, CameraProfileRevision.revision.desc())
        )
    ).all()
    return CameraProfileListResponse(
        items=[
            CameraProfileRevisionRead(**revision_read_payload(row, device_code)) for row in rows
        ],
        feature_enabled=bool(settings.CAMERA_CONTRACT_V2_ENABLED),
    )


@admin_router.post("", response_model=CameraProfileRevisionRead, status_code=201)
async def create_profile_revision(
    body: CameraProfileCreate,
    _claims: AdminCsrfDep,
    settings: SettingsDep,
    uow: UowDep,
) -> CameraProfileRevisionRead:
    try:
        row = await create_profile(
            uow.session,
            body,
            actor=str(_claims.get("sub") or "admin"),
            settings=settings,
        )
    except (CameraProfileError, ValueError) as exc:
        if isinstance(exc, CameraProfileError):
            raise _error(exc) from exc
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CameraProfileRevisionRead(**revision_read_payload(row, body.device_code))


@gateway_router.get("/capabilities", response_model=CameraCapabilitiesV1)
async def gateway_capabilities(
    _gateway_id: GatewayIdDep,
    settings: SettingsDep,
    uow: UowDep,
    device_code: str = Query(default="CAM-001", min_length=1, max_length=63),
    x_camera_capabilities_version: str | None = Header(
        default=None, alias="X-Camera-Capabilities-Version"
    ),
) -> CameraCapabilitiesV1:
    return await _capabilities(
        device_code,
        settings,
        uow,
        advertised_version=x_camera_capabilities_version,
    )
