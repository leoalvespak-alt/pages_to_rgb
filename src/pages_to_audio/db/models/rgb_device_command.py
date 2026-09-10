from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class RgbDeviceCommand(Base):
    """Auditable manual RGB command addressed to one physical device."""

    __tablename__ = "rgb_device_commands"
    __table_args__ = (
        UniqueConstraint("command_id", name="uq_rgb_device_commands_command_id"),
        CheckConstraint("kind IN ('TEST','STOP')", name="ck_rgb_device_commands_kind"),
        CheckConstraint(
            "status IN ("
            "'QUEUED','FORWARDED','RECEIVED','APPLIED','OFF',"
            "'EXPIRED','FAILED','CANCELLED')",
            name="ck_rgb_device_commands_status",
        ),
        CheckConstraint(
            "jsonb_typeof(rgb) = 'array' AND jsonb_array_length(rgb) = 3",
            name="ck_rgb_device_commands_rgb_shape",
        ),
        CheckConstraint(
            "brightness_percent BETWEEN 0 AND 100",
            name="ck_rgb_device_commands_brightness",
        ),
        CheckConstraint("on_ms BETWEEN 100 AND 60000", name="ck_rgb_device_commands_on_ms"),
        CheckConstraint("off_ms BETWEEN 0 AND 60000", name="ck_rgb_device_commands_off_ms"),
        CheckConstraint(
            "repeat_count BETWEEN 1 AND 20",
            name="ck_rgb_device_commands_repeat_count",
        ),
        CheckConstraint(
            "(on_ms + off_ms) * repeat_count <= 120000",
            name="ck_rgb_device_commands_duration",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_rgb_device_commands_attempt_count"),
        Index("ix_rgb_device_commands_device_status", "device_id", "status"),
        Index("ix_rgb_device_commands_device_expiry", "device_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    rgb: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    brightness_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    on_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    off_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    repeat_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'QUEUED'"))
    queued_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    forwarded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(nullable=True)
    off_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expired_at: Mapped[datetime | None] = mapped_column(nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
