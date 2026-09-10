"""Admin and gateway transport for audited physical RGB commands."""

from __future__ import annotations

from typing import Annotated, NoReturn
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select

from apps.api.dependencies import SettingsDep, UowDep
from apps.api.schemas.admin import (
    AdminDeviceListResponse,
    AdminDeviceRead,
    CameraCapabilitiesV1,
    RgbDeviceCommandListResponse,
    RgbDeviceCommandRead,
    RgbDeviceEventRequest,
    RgbDeviceTestRequest,
)
from src.pages_to_audio.auth.admin import AdminClaimsDep, AdminCsrfDep
from src.pages_to_audio.auth.gateway import verify_gateway_token
from src.pages_to_audio.camera_profiles.service import capabilities_payload, find_device
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.db.models.rgb_device_command import RgbDeviceCommand
from src.pages_to_audio.db.models.rgb_device_command_event import RgbDeviceCommandEvent
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.rgb.device_commands import (
    RgbCommandError,
    command_read_payload,
    create_manual_command,
    get_command,
    list_gateway_commands,
    record_event,
    stop_command,
)

admin_router = APIRouter(prefix="/admin/devices", tags=["admin-rgb-devices"])
gateway_router = APIRouter(
    prefix="/gateway/devices",
    tags=["gateway-rgb-devices"],
    dependencies=[Depends(verify_gateway_token)],
)
GatewayIdDep = Annotated[str, Depends(verify_gateway_token)]


def _raise_command_error(exc: RgbCommandError) -> NoReturn:
    raise HTTPException(
        status_code=exc.status_code,
        detail={"reason_code": exc.reason_code, "message": str(exc)},
    )


async def _gateway_is_enabled(uow: UowDep, gateway_code: str) -> None:
    gateway = await uow.session.scalar(
        select(AndroidGateway).where(
            AndroidGateway.gateway_code == gateway_code,
            AndroidGateway.enabled.is_(True),
        )
    )
    if gateway is None:
        raise HTTPException(
            status_code=403,
            detail={"reason_code": "GATEWAY_DISABLED", "message": "Gateway is not enabled"},
        )


async def _command_response(
    uow: UowDep,
    command: RgbDeviceCommand,
    device_code: str,
    *,
    idempotent: bool = False,
) -> RgbDeviceCommandRead:
    session_id = getattr(command, "session_id", None)
    session_public_id = None
    if session_id is not None:
        session_public_id = await uow.session.scalar(
            select(Session.public_id).where(Session.id == session_id)
        )
    latest_effective = await uow.session.scalar(
        select(RgbDeviceCommandEvent.effective_payload)
        .where(RgbDeviceCommandEvent.command_id == command.command_id)
        .order_by(RgbDeviceCommandEvent.received_at.desc())
        .limit(1)
    )
    return RgbDeviceCommandRead(
        **command_read_payload(
            command,
            device_code,
            session_public_id=session_public_id,
            effective_override=(
                latest_effective
                if isinstance(latest_effective, dict) and latest_effective
                else None
            ),
            idempotent=idempotent,
        )
    )


@admin_router.get("", response_model=AdminDeviceListResponse)
async def list_devices(_claims: AdminClaimsDep, uow: UowDep) -> AdminDeviceListResponse:
    devices = (
        await uow.session.scalars(select(Device).order_by(Device.device_code))
    ).all()
    return AdminDeviceListResponse(
        items=[
            AdminDeviceRead(
                device_code=device.device_code,
                display_name=device.display_name,
                enabled=device.enabled,
                firmware_version=device.firmware_version,
                camera_capabilities_version=str(
                    (device.metadata_ or {}).get("camera_capabilities_version")
                    or (device.metadata_ or {}).get("capabilities_version")
                    or ""
                )
                or None,
                capture_source=device.capture_source,
                last_seen_at=device.last_seen_at,
                telemetry=(device.metadata_ or {}).get("telemetry") or {},
            )
            for device in devices
        ]
    )


@admin_router.get(
    "/{device_code}/camera-capabilities", response_model=CameraCapabilitiesV1
)
async def device_camera_capabilities(
    device_code: str,
    _claims: AdminClaimsDep,
    uow: UowDep,
    settings: SettingsDep,
) -> CameraCapabilitiesV1:
    device = await find_device(uow.session, device_code)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")
    return CameraCapabilitiesV1(**capabilities_payload(device, settings))


@admin_router.post(
    "/{device_code}/rgb-tests", response_model=RgbDeviceCommandRead, status_code=201
)
async def create_rgb_test(
    device_code: str,
    body: RgbDeviceTestRequest,
    _claims: AdminCsrfDep,
    uow: UowDep,
) -> RgbDeviceCommandRead:
    try:
        command = await create_manual_command(
            uow.session,
            device_code=device_code,
            body=body,
            actor=str(_claims.get("sub") or "admin"),
        )
    except RgbCommandError as exc:
        _raise_command_error(exc)
    return await _command_response(uow, command, device_code)


@admin_router.get(
    "/{device_code}/rgb-tests/{command_id}", response_model=RgbDeviceCommandRead
)
async def read_rgb_test(
    device_code: str,
    command_id: UUID,
    _claims: AdminClaimsDep,
    uow: UowDep,
) -> RgbDeviceCommandRead:
    try:
        command, _device = await get_command(
            uow.session, device_code=device_code, command_id=command_id
        )
    except RgbCommandError as exc:
        _raise_command_error(exc)
    return await _command_response(uow, command, device_code)


@admin_router.post(
    "/{device_code}/rgb-tests/{command_id}/stop", response_model=RgbDeviceCommandRead
)
async def stop_rgb_test(
    device_code: str,
    command_id: UUID,
    _claims: AdminCsrfDep,
    uow: UowDep,
) -> RgbDeviceCommandRead:
    try:
        command, idempotent = await stop_command(
            uow.session,
            device_code=device_code,
            command_id=command_id,
            actor=str(_claims.get("sub") or "admin"),
        )
    except RgbCommandError as exc:
        _raise_command_error(exc)
    return await _command_response(uow, command, device_code, idempotent=idempotent)


@gateway_router.get("/{device_code}/commands", response_model=RgbDeviceCommandListResponse)
async def poll_rgb_commands(
    device_code: str,
    gateway_code: GatewayIdDep,
    uow: UowDep,
    after: int = Query(default=0, ge=0),
) -> RgbDeviceCommandListResponse:
    await _gateway_is_enabled(uow, gateway_code)
    try:
        _device, commands, cursor = await list_gateway_commands(
            uow.session,
            device_code=device_code,
            after_millis=after or None,
        )
    except RgbCommandError as exc:
        _raise_command_error(exc)
    return RgbDeviceCommandListResponse(
        items=[
            await _command_response(uow, command, device_code)
            for command in commands
        ],
        cursor=cursor,
    )


@gateway_router.post(
    "/{device_code}/commands/{command_id}/events",
    response_model=RgbDeviceCommandRead,
)
async def receive_rgb_command_event(
    device_code: str,
    command_id: UUID,
    body: RgbDeviceEventRequest,
    gateway_code: GatewayIdDep,
    uow: UowDep,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> RgbDeviceCommandRead:
    await _gateway_is_enabled(uow, gateway_code)
    try:
        command, duplicate = await record_event(
            uow.session,
            device_code=device_code,
            command_id=command_id,
            event=body.event,
            idempotency_key=idempotency_key or "",
            payload=body.payload,
            effective=body.effective_payload,
            firmware_version=body.firmware_version,
            device_timestamp=body.device_timestamp,
        )
    except RgbCommandError as exc:
        _raise_command_error(exc)
    return await _command_response(uow, command, device_code, idempotent=duplicate)
