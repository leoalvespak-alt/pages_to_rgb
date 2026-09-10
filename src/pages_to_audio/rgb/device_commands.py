"""Audited manual RGB commands for one physical device."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.common.errors import ReasonCode
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.rgb_device_command import RgbDeviceCommand
from src.pages_to_audio.db.models.rgb_device_command_event import RgbDeviceCommandEvent
from src.pages_to_audio.db.models.rgb_sequence import RgbSequence
from src.pages_to_audio.db.models.session import Session

ACTIVE_COMMAND_STATUSES = frozenset({"QUEUED", "FORWARDED", "RECEIVED", "APPLIED"})
COMMAND_LOCK_STATUSES = ACTIVE_COMMAND_STATUSES | {"CANCELLED"}
ACTIVE_SEQUENCE_STATUSES = frozenset({"READY", "RECEIVED", "PLAYING"})
EVENTS = Literal[
    "FORWARDED", "RECEIVED", "APPLIED", "OFF", "FAILED", "EXPIRED", "CANCELLED"
]


class RgbCommandError(Exception):
    def __init__(self, message: str, *, reason_code: str, status_code: int = 409) -> None:
        super().__init__(message)
        self.reason_code = reason_code
        self.status_code = status_code


def requested_payload(body: Any) -> dict[str, Any]:
    return {
        "rgb": list(body.rgb or (0, 0, 0)),
        "brightness_percent": body.brightness_percent,
        "on_ms": body.on_ms,
        "off_ms": body.off_ms,
        "repeat_count": body.repeat_count,
    }


def effective_payload(command: RgbDeviceCommand) -> dict[str, Any]:
    return {
        "rgb": list(command.rgb),
        "brightness_percent": command.brightness_percent,
        "on_ms": command.on_ms,
        "off_ms": command.off_ms,
        "repeat_count": command.repeat_count,
    }


def command_read_payload(
    command: RgbDeviceCommand,
    device_code: str,
    *,
    session_public_id: str | None = None,
    effective_override: dict[str, Any] | None = None,
    idempotent: bool = False,
) -> dict[str, Any]:
    requested = effective_payload(command)
    return {
        "command_id": str(command.command_id),
        "device_code": device_code,
        "session_id": session_public_id,
        "kind": command.kind,
        "status": command.status,
        "requested": requested,
        "effective": effective_override or requested,
        "expires_at": command.expires_at,
        "failure_reason": command.failure_reason,
        "idempotent": idempotent,
    }


async def _device(session: AsyncSession, device_code: str) -> Device:
    device = await session.scalar(
        select(Device).where(Device.device_code == device_code).with_for_update()
    )
    if device is None:
        raise RgbCommandError(
            "Device not found", reason_code=ReasonCode.DEVICE_UNKNOWN.value, status_code=404
        )
    if not device.enabled:
        raise RgbCommandError(
            "Device is disabled", reason_code=ReasonCode.DEVICE_DISABLED.value, status_code=403
        )
    return device


async def _active_sequence(session: AsyncSession, device_id: uuid.UUID) -> RgbSequence | None:
    return await session.scalar(
        select(RgbSequence)
        .join(Session, RgbSequence.session_id == Session.id)
        .where(
            Session.device_id == device_id,
            RgbSequence.status.in_(ACTIVE_SEQUENCE_STATUSES),
        )
        .limit(1)
    )


async def _expire_overdue(session: AsyncSession, device: Device) -> None:
    now = datetime.now(UTC)
    rows = (
        await session.scalars(
            select(RgbDeviceCommand)
            .where(
                RgbDeviceCommand.device_id == device.id,
                RgbDeviceCommand.status.in_(ACTIVE_COMMAND_STATUSES),
                RgbDeviceCommand.expires_at <= now,
            )
            .with_for_update()
        )
    ).all()
    for command in rows:
        command.status = "EXPIRED"
        command.expired_at = now
        command.failure_reason = "command_timeout"
        event_key = f"timeout:{command.command_id}"
        session.add(
            RgbDeviceCommandEvent(
                command_id=command.command_id,
                device_id=device.id,
                event_type="EXPIRED",
                requested_payload=effective_payload(command),
                effective_payload={},
                payload={"reason": "command_timeout"},
                firmware_version=device.firmware_version,
                error="command_timeout",
                idempotency_key=event_key,
            )
        )
        session.add(
            AuditEvent(
                event_type="RGB_DEVICE_COMMAND_EXPIRED",
                stage="DELIVER",
                severity="WARNING",
                reason_code="RGB_COMMAND_TIMEOUT",
                actor_type="system",
                payload={"command_id": str(command.command_id)},
            )
        )


async def create_manual_command(
    session: AsyncSession,
    *,
    device_code: str,
    body: Any,
    actor: str,
) -> RgbDeviceCommand:
    device = await _device(session, device_code)
    await _expire_overdue(session, device)
    active = await session.scalar(
        select(RgbDeviceCommand)
        .where(
            RgbDeviceCommand.device_id == device.id,
            RgbDeviceCommand.status.in_(COMMAND_LOCK_STATUSES),
        )
        .with_for_update()
    )
    if active is not None:
        raise RgbCommandError(
            "A manual RGB test is already active for this device",
            reason_code="RGB_TEST_BUSY",
        )
    sequence = await _active_sequence(session, device.id)
    if sequence is not None:
        raise RgbCommandError(
            "A real RGB sequence is active for this device",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT.value,
        )
    linked_session = None
    if body.session_id:
        linked_session = await session.scalar(
            select(Session).where(Session.public_id == body.session_id)
        )
        if linked_session is None:
            raise RgbCommandError(
                "Session not found", reason_code=ReasonCode.SESSION_NOT_FOUND.value, status_code=404
            )
        if linked_session.device_id != device.id:
            raise RgbCommandError(
                "Session is not bound to this device",
                reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT.value,
            )
    now = datetime.now(UTC)
    duration_s = ((body.on_ms + body.off_ms) * body.repeat_count) / 1000
    command = RgbDeviceCommand(
        command_id=uuid.uuid4(),
        device_id=device.id,
        session_id=linked_session.id if linked_session is not None else None,
        kind="TEST",
        rgb=list(body.rgb),
        brightness_percent=body.brightness_percent,
        on_ms=body.on_ms,
        off_ms=body.off_ms,
        repeat_count=body.repeat_count,
        status="QUEUED",
        expires_at=now + timedelta(seconds=max(30, duration_s + 30)),
        created_by=actor,
    )
    session.add(command)
    session.add(
        AuditEvent(
            session_id=linked_session.id if linked_session is not None else None,
            event_type="RGB_DEVICE_COMMAND_CREATED",
            stage="DELIVER",
            severity="INFO",
            actor_type="admin",
            payload={
                "command_id": str(command.command_id),
                "device_code": device_code,
                "requested": requested_payload(body),
                "effective": requested_payload(body),
            },
        )
    )
    await session.flush()
    return command


async def get_command(
    session: AsyncSession, *, device_code: str, command_id: uuid.UUID
) -> tuple[RgbDeviceCommand, Device]:
    device = await _device(session, device_code)
    await _expire_overdue(session, device)
    command = await session.scalar(
        select(RgbDeviceCommand).where(
            RgbDeviceCommand.device_id == device.id,
            RgbDeviceCommand.command_id == command_id,
        )
    )
    if command is None:
        raise RgbCommandError(
            "RGB command not found", reason_code=ReasonCode.NOT_FOUND.value, status_code=404
        )
    return command, device


async def stop_command(
    session: AsyncSession, *, device_code: str, command_id: uuid.UUID, actor: str
) -> tuple[RgbDeviceCommand, bool]:
    command, device = await get_command(session, device_code=device_code, command_id=command_id)
    if command.status in {"OFF", "CANCELLED", "EXPIRED", "FAILED"}:
        return command, True
    now = datetime.now(UTC)
    command.status = "CANCELLED"
    command.cancelled_at = now
    session.add(
        RgbDeviceCommandEvent(
            command_id=command.command_id,
            device_id=device.id,
            event_type="CANCELLED",
            requested_payload=effective_payload(command),
            effective_payload={},
            payload={"actor": actor},
            firmware_version=device.firmware_version,
            idempotency_key=f"stop:{command.command_id}",
        )
    )
    session.add(
        AuditEvent(
            session_id=command.session_id,
            event_type="RGB_DEVICE_COMMAND_STOP_REQUESTED",
            stage="DELIVER",
            severity="INFO",
            actor_type="admin",
            payload={"command_id": str(command.command_id)},
        )
    )
    await session.flush()
    return command, False


async def list_gateway_commands(
    session: AsyncSession,
    *,
    device_code: str,
    after_millis: int | None = None,
    limit: int = 100,
) -> tuple[Device, list[RgbDeviceCommand], int]:
    device = await _device(session, device_code)
    query = (
        select(RgbDeviceCommand)
        .where(
            RgbDeviceCommand.device_id == device.id,
            RgbDeviceCommand.status.in_(COMMAND_LOCK_STATUSES),
        )
        .order_by(RgbDeviceCommand.queued_at, RgbDeviceCommand.command_id)
        .limit(limit)
    )
    if after_millis is not None:
        after = datetime.fromtimestamp(after_millis / 1000, UTC)
        query = query.where(RgbDeviceCommand.queued_at > after)
    commands = list((await session.scalars(query)).all())
    cursor = after_millis or 0
    for command in commands:
        queued_at = command.queued_at
        if queued_at.tzinfo is None:
            queued_at = queued_at.replace(tzinfo=UTC)
        cursor = max(cursor, int(queued_at.timestamp() * 1000))
    return device, commands, cursor


def _next_status(current: str, event: EVENTS) -> str:
    allowed: dict[str, set[str]] = {
        "FORWARDED": {"QUEUED", "FORWARDED"},
        "RECEIVED": {"FORWARDED", "RECEIVED"},
        "APPLIED": {"RECEIVED", "APPLIED"},
        "OFF": {"APPLIED", "CANCELLED", "OFF"},
        "FAILED": set(ACTIVE_COMMAND_STATUSES),
        "EXPIRED": set(ACTIVE_COMMAND_STATUSES),
        "CANCELLED": set(ACTIVE_COMMAND_STATUSES) | {"CANCELLED"},
    }
    if current not in allowed[event]:
        raise RgbCommandError(
            f"Event {event} is invalid after status {current}",
            reason_code="RGB_COMMAND_INVALID_TRANSITION",
        )
    if event == "CANCELLED":
        return "CANCELLED"
    return event


async def record_event(
    session: AsyncSession,
    *,
    device_code: str,
    command_id: uuid.UUID,
    event: EVENTS,
    idempotency_key: str,
    payload: dict[str, Any],
    effective: dict[str, Any],
    firmware_version: str | None,
    device_timestamp: datetime | None,
) -> tuple[RgbDeviceCommand, bool]:
    if not idempotency_key:
        raise RgbCommandError(
            "Idempotency-Key is required",
            reason_code=ReasonCode.INVALID_REQUEST.value,
            status_code=422,
        )
    command, device = await get_command(session, device_code=device_code, command_id=command_id)
    existing = await session.scalar(
        select(RgbDeviceCommandEvent).where(
            RgbDeviceCommandEvent.command_id == command.command_id,
            RgbDeviceCommandEvent.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if existing.payload != payload:
            raise RgbCommandError(
                "Idempotency-Key was reused with different payload",
                reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD.value,
            )
        return command, True
    status = _next_status(command.status, event)
    now = datetime.now(UTC)
    if event == "APPLIED" and now >= command.expires_at:
        raise RgbCommandError("RGB command expired", reason_code="RGB_COMMAND_TIMEOUT")
    command.status = status
    if event == "FORWARDED":
        command.forwarded_at = command.forwarded_at or now
        command.attempt_count = int(command.attempt_count or 0) + 1
    elif event == "RECEIVED":
        command.received_at = now
    elif event == "APPLIED":
        command.applied_at = now
    elif event == "OFF":
        command.off_at = now
    elif event == "FAILED":
        command.failed_at = now
        command.failure_reason = str(payload.get("reason") or "device_failed")
    elif event == "EXPIRED":
        command.expired_at = now
    elif event == "CANCELLED":
        command.cancelled_at = now
    session.add(
        RgbDeviceCommandEvent(
            command_id=command.command_id,
            device_id=device.id,
            event_type=event,
            requested_payload=effective_payload(command),
            effective_payload=effective,
            payload=payload,
            firmware_version=firmware_version or device.firmware_version,
            device_timestamp=device_timestamp,
            error=payload.get("error") if isinstance(payload.get("error"), str) else None,
            idempotency_key=idempotency_key,
        )
    )
    session.add(
        AuditEvent(
            session_id=command.session_id,
            event_type="RGB_DEVICE_COMMAND_EVENT",
            stage="DELIVER",
            severity="ERROR" if event in {"FAILED", "EXPIRED"} else "INFO",
            reason_code=payload.get("reason") if isinstance(payload.get("reason"), str) else None,
            actor_type="gateway",
            payload={
                "command_id": str(command.command_id),
                "event": event,
                "payload": payload,
                "effective": effective,
            },
        )
    )
    await session.flush()
    return command, False
