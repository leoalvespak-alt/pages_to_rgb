from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class RgbDeviceCommandEvent(Base):
    """Idempotent device event proving transport or physical RGB progress."""

    __tablename__ = "rgb_device_command_events"
    __table_args__ = (
        UniqueConstraint(
            "command_id",
            "idempotency_key",
            name="uq_rgb_device_command_events_command_idempotency",
        ),
        CheckConstraint(
            "event_type IN ('FORWARDED','RECEIVED','APPLIED','OFF','FAILED','EXPIRED','CANCELLED')",
            name="ck_rgb_device_command_events_type",
        ),
        Index(
            "ix_rgb_device_command_events_command_received",
            "command_id",
            "received_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    command_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rgb_device_commands.command_id", ondelete="CASCADE"),
        nullable=False,
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    requested_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    effective_payload: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    firmware_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_timestamp: Mapped[datetime | None] = mapped_column(nullable=True)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
