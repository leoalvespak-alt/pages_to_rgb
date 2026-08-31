"""Persistence and delivery services for firmware V2.2 RGB results."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.pages_to_audio.common.errors import AppError, ReasonCode
from src.pages_to_audio.config.settings import get_settings
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.gateway import AndroidGateway
from src.pages_to_audio.db.models.rgb_sequence import RgbSequence
from src.pages_to_audio.db.models.rgb_sequence_event import RgbSequenceEvent
from src.pages_to_audio.db.models.session import Session
from src.pages_to_audio.db.models.session_result_delivery import SessionResultDelivery
from src.pages_to_audio.domain.enums.audit import AuditEventType, AuditSeverity, AuditStage
from src.pages_to_audio.domain.enums.session_state import SessionState
from src.pages_to_audio.rgb.canonical import compact_json_bytes, validate_payload_sha256
from src.pages_to_audio.rgb.schemas import (
    RgbEventName,
    RgbResultCommand,
    RgbSequencePayload,
    RgbSequenceStatus,
)


class RgbApiError(AppError):
    """Expected error that can be safely returned by a gateway endpoint."""


@dataclass(frozen=True, slots=True)
class SessionBinding:
    session: Session
    device: Device
    gateway: AndroidGateway


@dataclass(frozen=True, slots=True)
class ResultSnapshot:
    command: RgbResultCommand
    cursor: int
    session_id: str
    sequence_id: str | None = None
    revision: int | None = None
    item_count: int | None = None
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class RecordedRgbEvent:
    sequence: RgbSequence
    duplicate: bool


_NOT_STARTED_STATES = {
    SessionState.CREATED,
    SessionState.CAPTURING,
    SessionState.CAPTURE_END_CANDIDATE,
    SessionState.CAPTURE_LOCKING,
    SessionState.LOCKED,
}
_PROCESSING_STATES = {
    SessionState.IMAGE_PROCESSING,
    SessionState.OCR_PROCESSING,
    SessionState.RECONSTRUCTING,
    SessionState.RESCUE_PROCESSING,
    SessionState.GATE_1,
    SessionState.RAG_RETRIEVING,
    SessionState.SOLVING,
    SessionState.VERIFYING,
    SessionState.ARBITRATING,
    SessionState.GATE_2,
    SessionState.STATUS_AUDIO,
    SessionState.TTS_GENERATING,
    SessionState.AUDIO_ASSEMBLING,
    SessionState.AUDIO_VALIDATING,
    SessionState.FAILED_RECOVERABLE,
}
_CANCELLED_STATES = {
    SessionState.BLOCKED_GATE_1,
    SessionState.BLOCKED_GATE_2,
    SessionState.FAILED_FATAL,
    SessionState.CANCELLED,
}


def derive_command(session: Session) -> RgbResultCommand:
    """Map existing session processing state to the firmware result command."""

    try:
        state = SessionState(session.status)
    except ValueError:
        return RgbResultCommand.RESULT_PROCESSING
    if state in _NOT_STARTED_STATES and session.processing_started_at is None:
        return RgbResultCommand.RESULT_NOT_STARTED
    if state in _CANCELLED_STATES:
        return RgbResultCommand.RESULT_CANCELLED
    if state in {SessionState.READY, SessionState.COMPLETED}:
        return RgbResultCommand.RESULT_CANCELLED
    if state in _PROCESSING_STATES:
        return RgbResultCommand.RESULT_PROCESSING
    return RgbResultCommand.RESULT_PROCESSING


async def get_session_binding(
    db: AsyncSession,
    *,
    session_public_id: str,
    device_code: str,
    gateway_code: str,
) -> SessionBinding:
    """Resolve and authorize the gateway/device/session relationship."""

    stmt = (
        select(Session, Device, AndroidGateway)
        .join(Device, Session.device_id == Device.id)
        .join(AndroidGateway, Session.gateway_id == AndroidGateway.id)
        .where(
            Session.public_id == session_public_id,
            Device.device_code == device_code,
            AndroidGateway.gateway_code == gateway_code,
        )
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise RgbApiError(
            "Session not found",
            reason_code=ReasonCode.SESSION_NOT_FOUND,
            http_status=404,
        )
    session, device, gateway = row
    if not device.enabled:
        raise RgbApiError(
            "Device is disabled",
            reason_code=ReasonCode.DEVICE_DISABLED,
            http_status=403,
        )
    if not gateway.enabled:
        raise RgbApiError(
            "Gateway is disabled",
            reason_code=ReasonCode.GATEWAY_DISABLED,
            http_status=403,
        )
    return SessionBinding(session=session, device=device, gateway=gateway)


async def get_or_create_delivery(
    db: AsyncSession,
    binding: SessionBinding,
    *,
    command: RgbResultCommand,
    active_sequence_id: uuid.UUID | None = None,
    reason_code: str | None = None,
) -> SessionResultDelivery:
    """Create or atomically advance a session's visible result command."""

    stmt = (
        select(SessionResultDelivery)
        .where(SessionResultDelivery.session_id == binding.session.id)
        .with_for_update()
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if delivery is None:
        delivery = SessionResultDelivery(
            session_id=binding.session.id,
            device_id=binding.device.id,
            gateway_id=binding.gateway.id,
            command=command.value,
            cursor=1,
            active_sequence_id=active_sequence_id,
            reason_code=reason_code,
        )
        db.add(delivery)
        db.add(
            AuditEvent(
                session_id=binding.session.id,
                event_type=AuditEventType.RGB_RESULT_STATUS_CHANGED,
                stage=AuditStage.SYSTEM,
                severity=AuditSeverity.WARNING
                if command is RgbResultCommand.RESULT_CANCELLED
                else AuditSeverity.INFO,
                actor_type="system",
                payload={
                    "command": command.value,
                    "cursor": 1,
                    "active_sequence_id": str(active_sequence_id)
                    if active_sequence_id is not None
                    else None,
                    "reason_code": reason_code,
                },
            )
        )
        await db.flush()
        return delivery

    if delivery.device_id != binding.device.id or delivery.gateway_id != binding.gateway.id:
        raise RgbApiError(
            "Result delivery binding conflict",
            reason_code=ReasonCode.FORBIDDEN,
            http_status=403,
        )

    changed = (
        delivery.command != command.value
        or delivery.active_sequence_id != active_sequence_id
        or delivery.reason_code != reason_code
    )
    if changed:
        previous_command = delivery.command
        previous_cursor = delivery.cursor
        delivery.command = command.value
        delivery.active_sequence_id = active_sequence_id
        delivery.reason_code = reason_code
        delivery.cursor += 1
        delivery.updated_at = datetime.now(UTC)
        db.add(
            AuditEvent(
                session_id=binding.session.id,
                event_type=AuditEventType.RGB_RESULT_STATUS_CHANGED,
                stage=AuditStage.SYSTEM,
                severity=AuditSeverity.WARNING
                if command is RgbResultCommand.RESULT_CANCELLED
                else AuditSeverity.INFO,
                actor_type="system",
                payload={
                    "previous_command": previous_command,
                    "command": command.value,
                    "previous_cursor": previous_cursor,
                    "cursor": delivery.cursor,
                    "active_sequence_id": str(active_sequence_id)
                    if active_sequence_id is not None
                    else None,
                    "reason_code": reason_code,
                },
            )
        )
        await db.flush()
    return delivery


async def mark_result_processing(
    db: AsyncSession,
    binding: SessionBinding,
) -> SessionResultDelivery:
    """Make an active workflow visible to the next firmware poll."""

    current = await db.scalar(
        select(SessionResultDelivery).where(
            SessionResultDelivery.session_id == binding.session.id,
        )
    )
    if current is not None and current.command == RgbResultCommand.RGB_SEQUENCE_READY.value:
        return current
    return await get_or_create_delivery(
        db,
        binding,
        command=RgbResultCommand.RESULT_PROCESSING,
    )


async def result_snapshot(
    db: AsyncSession,
    binding: SessionBinding,
    *,
    cursor: int,
) -> ResultSnapshot | None:
    """Return a new result command, or None when the cursor is current."""

    delivery = await db.scalar(
        select(SessionResultDelivery).where(
            SessionResultDelivery.session_id == binding.session.id,
            SessionResultDelivery.device_id == binding.device.id,
            SessionResultDelivery.gateway_id == binding.gateway.id,
        )
    )
    if delivery is None:
        command = derive_command(binding.session)
        if cursor >= 1:
            return None
        return ResultSnapshot(command=command, cursor=1, session_id=binding.session.public_id)

    if cursor >= delivery.cursor:
        return None

    snapshot = ResultSnapshot(
        command=RgbResultCommand(delivery.command),
        cursor=delivery.cursor,
        session_id=binding.session.public_id,
    )
    if delivery.active_sequence_id is None:
        return snapshot

    sequence = await db.scalar(
        select(RgbSequence).where(RgbSequence.id == delivery.active_sequence_id)
    )
    if sequence is None or sequence.status in {
        RgbSequenceStatus.INVALID.value,
        RgbSequenceStatus.SUPERSEDED.value,
    }:
        return ResultSnapshot(
            command=RgbResultCommand.RESULT_CANCELLED,
            cursor=delivery.cursor,
            session_id=binding.session.public_id,
        )
    return ResultSnapshot(
        command=RgbResultCommand(delivery.command),
        cursor=delivery.cursor,
        session_id=binding.session.public_id,
        sequence_id=sequence.sequence_id,
        revision=sequence.revision,
        item_count=sequence.item_count,
        sha256=sequence.payload_sha256,
    )


def sequence_payload(
    sequence: RgbSequence,
    *,
    session_public_id: str,
) -> tuple[RgbSequencePayload, bytes]:
    """Rehydrate and verify an immutable database sequence."""

    payload = RgbSequencePayload.model_validate(
        {
            "schema_version": sequence.schema_version,
            "session_id": session_public_id,
            "sequence_id": sequence.sequence_id,
            "revision": sequence.revision,
            "item_count": sequence.item_count,
            "sha256": sequence.payload_sha256,
            "answers": sequence.answers,
            "defaults": sequence.defaults,
            "palette": sequence.palette,
            "overrides": sequence.overrides,
        }
    )
    validate_payload_sha256(payload)
    raw = compact_json_bytes(payload)
    if len(raw) > get_settings().RGB_SEQUENCE_MAX_JSON_BYTES:
        raise RgbApiError(
            "RGB sequence exceeds firmware JSON limit",
            reason_code=ReasonCode.RGB_SEQUENCE_INVALID,
            http_status=409,
        )
    return payload, raw


async def get_sequence_for_binding(
    db: AsyncSession,
    binding: SessionBinding,
    *,
    sequence_id: str,
) -> tuple[RgbSequencePayload, bytes]:
    """Fetch a sequence only after validating its device/gateway/session binding."""

    sequence = await db.scalar(
        select(RgbSequence).where(
            RgbSequence.session_id == binding.session.id,
            RgbSequence.sequence_id == sequence_id,
        )
    )
    if sequence is None:
        raise RgbApiError(
            "RGB sequence not found",
            reason_code=ReasonCode.RGB_SEQUENCE_NOT_FOUND,
            http_status=404,
        )
    if sequence.status in {
        RgbSequenceStatus.INVALID.value,
        RgbSequenceStatus.SUPERSEDED.value,
    }:
        raise RgbApiError(
            "RGB sequence revision is no longer deliverable",
            reason_code=ReasonCode.RGB_SEQUENCE_NOT_FOUND,
            http_status=410,
        )
    return sequence_payload(sequence, session_public_id=binding.session.public_id)


def _event_identity(
    *,
    binding: SessionBinding,
    sequence: RgbSequence,
    event: RgbEventName,
    next_index: int,
) -> str:
    suffix = "" if event is RgbEventName.COMPLETED else f":{next_index}"
    return f"{binding.device.id}:{sequence.id}:{sequence.revision}:{event.value}{suffix}"


async def record_rgb_event(
    db: AsyncSession,
    binding: SessionBinding,
    *,
    session_id: str,
    sequence_id: str,
    revision: int,
    event: RgbEventName,
    next_index: int,
    item_count: int,
    idempotency_key: str | None,
    raw_payload: dict[str, Any],
) -> RecordedRgbEvent:
    """Record a device event under a sequence row lock and update its progress."""

    if session_id != binding.session.public_id:
        raise RgbApiError(
            "Event session_id does not match route",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
            http_status=409,
        )
    sequence = await db.scalar(
        select(RgbSequence)
        .where(
            RgbSequence.session_id == binding.session.id,
            RgbSequence.sequence_id == sequence_id,
            RgbSequence.revision == revision,
        )
        .with_for_update()
    )
    if sequence is None:
        raise RgbApiError(
            "RGB sequence not found",
            reason_code=ReasonCode.RGB_SEQUENCE_NOT_FOUND,
            http_status=404,
        )
    if item_count != sequence.item_count or not 0 <= next_index <= item_count:
        raise RgbApiError(
            "RGB event progress does not match the sequence",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
            http_status=409,
        )

    identity = _event_identity(
        binding=binding,
        sequence=sequence,
        event=event,
        next_index=next_index,
    )
    if idempotency_key:
        key_event = await db.scalar(
            select(RgbSequenceEvent).where(
                RgbSequenceEvent.idempotency_key == idempotency_key,
                RgbSequenceEvent.gateway_id == binding.gateway.id,
            )
        )
        if key_event is not None:
            if key_event.payload != raw_payload:
                raise RgbApiError(
                    "Idempotency-Key was reused with a different payload",
                    reason_code=ReasonCode.IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD,
                    http_status=409,
                )
            return RecordedRgbEvent(sequence=sequence, duplicate=True)
    existing = await db.scalar(
        select(RgbSequenceEvent).where(RgbSequenceEvent.event_identity == identity)
    )
    if existing is not None:
        if existing.payload != raw_payload:
            raise RgbApiError(
                "RGB event identity was reused with a different payload",
                reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
                http_status=409,
            )
        return RecordedRgbEvent(sequence=sequence, duplicate=True)

    if sequence.status in {
        RgbSequenceStatus.INVALID.value,
        RgbSequenceStatus.SUPERSEDED.value,
    }:
        raise RgbApiError(
            "RGB sequence is not deliverable",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
            http_status=409,
        )
    if sequence.status == RgbSequenceStatus.COMPLETED.value and event is not RgbEventName.COMPLETED:
        raise RgbApiError(
            "RGB sequence is already completed",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
            http_status=409,
        )
    if event is RgbEventName.RECEIVED and sequence.status != RgbSequenceStatus.READY.value:
        raise RgbApiError(
            "RECEIVED is only valid for a ready RGB sequence",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
            http_status=409,
        )
    if next_index < sequence.last_next_index:
        raise RgbApiError(
            "RGB sequence progress cannot move backwards",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
            http_status=409,
        )
    if event is RgbEventName.COMPLETED and next_index != item_count:
        raise RgbApiError(
            "COMPLETED requires next_index equal to item_count",
            reason_code=ReasonCode.RGB_SEQUENCE_CONFLICT,
            http_status=409,
        )

    sequence.last_next_index = max(sequence.last_next_index, next_index)
    if event is RgbEventName.RECEIVED:
        sequence.status = RgbSequenceStatus.RECEIVED.value
    elif event in {RgbEventName.STARTED, RgbEventName.RESUMED}:
        sequence.status = RgbSequenceStatus.PLAYING.value
    elif event is RgbEventName.COMPLETED:
        sequence.status = RgbSequenceStatus.COMPLETED.value
        sequence.completed_at = datetime.now(UTC)
    else:
        sequence.status = RgbSequenceStatus.INVALID.value

    db.add(
        RgbSequenceEvent(
            rgb_sequence_id=sequence.id,
            device_id=binding.device.id,
            gateway_id=binding.gateway.id,
            event=event.value,
            next_index=next_index,
            item_count=item_count,
            idempotency_key=idempotency_key,
            event_identity=identity,
            payload=raw_payload,
        )
    )
    if event is RgbEventName.INVALID:
        await get_or_create_delivery(
            db,
            binding,
            command=RgbResultCommand.RESULT_CANCELLED,
            reason_code="RGB_SEQUENCE_INVALID_REPORTED_BY_DEVICE",
        )
    db.add(
        AuditEvent(
            session_id=binding.session.id,
            event_type=(
                AuditEventType.RGB_SEQUENCE_INVALID
                if event is RgbEventName.INVALID
                else AuditEventType.RGB_SEQUENCE_EVENT_RECEIVED
            ),
            stage=AuditStage.SYSTEM,
            severity=(AuditSeverity.ERROR if event is RgbEventName.INVALID else AuditSeverity.INFO),
            actor_type="gateway",
            payload={
                "sequence_id": sequence.sequence_id,
                "revision": sequence.revision,
                "event": event.value,
                "next_index": next_index,
                "item_count": item_count,
            },
        )
    )
    await db.flush()
    return RecordedRgbEvent(sequence=sequence, duplicate=False)
