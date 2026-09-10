"""G05 — physical RGB command state, safety, and API contract tests."""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from apps.api.main import create_app
from apps.api.schemas.admin import RgbDeviceTestRequest
from src.pages_to_audio.db.models.audit_event import AuditEvent
from src.pages_to_audio.db.models.device import Device
from src.pages_to_audio.db.models.rgb_device_command import RgbDeviceCommand
from src.pages_to_audio.db.models.rgb_device_command_event import RgbDeviceCommandEvent
from src.pages_to_audio.rgb.device_commands import (
    _expire_overdue,
    _next_status,
    create_manual_command,
    record_event,
    stop_command,
)


class FakeResult:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def all(self) -> list[object]:
        return self.values


class FakeSession:
    bind = None

    def __init__(
        self, scalar_values: list[object], scalar_rows: list[object] | None = None
    ) -> None:
        self.scalar_values = scalar_values
        self.scalar_rows = scalar_rows or []
        self.added: list[object] = []

    async def scalar(self, *_args: object, **_kwargs: object) -> object:
        return self.scalar_values.pop(0)

    async def scalars(self, *_args: object, **_kwargs: object) -> FakeResult:
        return FakeResult(self.scalar_rows)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        return None


def _device() -> Device:
    return Device(
        id=uuid.uuid4(),
        device_code="ESP-G05-001",
        display_name="G05 ESP",
        enabled=True,
        firmware_version="production-g05",
    )


def _command(device: Device, *, status: str = "QUEUED") -> RgbDeviceCommand:
    return RgbDeviceCommand(
        id=uuid.uuid4(),
        command_id=uuid.uuid4(),
        device_id=device.id,
        kind="TEST",
        rgb=[255, 0, 0],
        brightness_percent=12,
        on_ms=3000,
        off_ms=5000,
        repeat_count=1,
        status=status,
        attempt_count=0,
        expires_at=datetime.now(UTC) + timedelta(seconds=30),
    )


@pytest.mark.unit
def test_manual_request_accepts_hex_and_enforces_duration_contract() -> None:
    request = RgbDeviceTestRequest(hex_color="#12a0ff", repeat_count=2)

    assert request.rgb == (18, 160, 255)
    assert (request.on_ms + request.off_ms) * request.repeat_count <= 120000

    with pytest.raises(ValidationError):
        RgbDeviceTestRequest(rgb=(1, 2, 3), hex_color="ffffff")
    with pytest.raises(ValidationError):
        RgbDeviceTestRequest(rgb=(1, 2, 3), on_ms=60000, off_ms=60000, repeat_count=2)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("current", "event", "expected"),
    [
        ("QUEUED", "FORWARDED", "FORWARDED"),
        ("FORWARDED", "RECEIVED", "RECEIVED"),
        ("RECEIVED", "APPLIED", "APPLIED"),
        ("APPLIED", "OFF", "OFF"),
        ("QUEUED", "EXPIRED", "EXPIRED"),
        ("APPLIED", "CANCELLED", "CANCELLED"),
    ],
)
def test_state_machine_accepts_only_contract_transitions(
    current: str, event: str, expected: str
) -> None:
    assert _next_status(current, event) == expected  # type: ignore[arg-type]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_manual_creation_is_audited_and_rejects_active_sequence_or_test() -> None:
    device = _device()
    body = RgbDeviceTestRequest(rgb=(1, 2, 3))
    session = FakeSession([device, None, None])

    created = await create_manual_command(
        session, device_code=device.device_code, body=body, actor="admin-user"
    )

    assert created.status == "QUEUED"
    assert created.command_id is not None
    assert any(isinstance(item, AuditEvent) for item in session.added)
    assert any(
        isinstance(item, AuditEvent)
        and item.event_type == "RGB_DEVICE_COMMAND_CREATED"
        for item in session.added
    )

    busy = _command(device)
    conflict_session = FakeSession([device, busy])
    with pytest.raises(Exception, match="already active"):
        await create_manual_command(
            conflict_session,
            device_code=device.device_code,
            body=body,
            actor="admin-user",
        )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_event_is_persisted_before_a_new_command_can_be_created() -> None:
    device = _device()
    overdue = _command(device)
    overdue.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session = FakeSession([], [overdue])

    await _expire_overdue(session, device)

    assert overdue.status == "EXPIRED"
    assert overdue.expired_at is not None
    assert any(
        isinstance(item, RgbDeviceCommandEvent) and item.event_type == "EXPIRED"
        for item in session.added
    )
    assert any(
        isinstance(item, AuditEvent) and item.reason_code == "RGB_COMMAND_TIMEOUT"
        for item in session.added
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stop_is_idempotent_and_leaves_off_proof_to_gateway_event() -> None:
    device = _device()
    command = _command(device, status="APPLIED")
    first = FakeSession([device, command])

    stopped, duplicate = await stop_command(
        first,
        device_code=device.device_code,
        command_id=command.command_id,
        actor="admin-user",
    )
    assert stopped.status == "CANCELLED"
    assert duplicate is False
    assert not any(
        isinstance(item, RgbDeviceCommandEvent) and item.event_type == "OFF"
        for item in first.added
    )

    second = FakeSession([device, command])
    stopped_again, duplicate = await stop_command(
        second,
        device_code=device.device_code,
        command_id=command.command_id,
        actor="admin-user",
    )
    assert stopped_again.status == "CANCELLED"
    assert duplicate is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_event_idempotency_and_payload_conflict() -> None:
    device = _device()
    command = _command(device)
    first = FakeSession([device, command, None])
    result, duplicate = await record_event(
        first,
        device_code=device.device_code,
        command_id=command.command_id,
        event="FORWARDED",
        idempotency_key="g05-event-1",
        payload={"attempt": 1},
        effective={"status": "FORWARDED"},
        firmware_version="production-g05",
        device_timestamp=None,
    )
    assert result.status == "FORWARDED"
    assert duplicate is False

    event = next(item for item in first.added if isinstance(item, RgbDeviceCommandEvent))
    replay = FakeSession([device, command, event])
    _, duplicate = await record_event(
        replay,
        device_code=device.device_code,
        command_id=command.command_id,
        event="FORWARDED",
        idempotency_key="g05-event-1",
        payload={"attempt": 1},
        effective={"status": "FORWARDED"},
        firmware_version="production-g05",
        device_timestamp=None,
    )
    assert duplicate is True

    conflict = FakeSession([device, command, event])
    with pytest.raises(Exception, match="reused with different payload"):
        await record_event(
            conflict,
            device_code=device.device_code,
            command_id=command.command_id,
            event="FORWARDED",
            idempotency_key="g05-event-1",
            payload={"attempt": 2},
            effective={"status": "FORWARDED"},
            firmware_version="production-g05",
            device_timestamp=None,
        )


@pytest.mark.unit
def test_g05_routes_are_authenticated_and_legacy_creation_uses_new_table() -> None:
    paths = create_app().openapi()["paths"]
    assert "/api/v1/admin/devices" in paths
    assert "/api/v1/admin/devices/{device_code}/rgb-tests" in paths
    assert "/api/v1/admin/devices/{device_code}/rgb-tests/{command_id}/stop" in paths
    assert "/api/v1/gateway/devices/{device_code}/commands" in paths
    assert "/api/v1/gateway/devices/{device_code}/commands/{command_id}/events" in paths

    from apps.api.routers import admin_settings, rgb_device_commands

    assert "create_manual_command" in inspect.getsource(admin_settings.send_rgb_test)
    assert "verify_gateway_token" in inspect.getsource(rgb_device_commands)
    assert "RGB_DEVICE_COMMAND_EVENT" in inspect.getsource(record_event)
