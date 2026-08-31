from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class SessionResultDelivery(Base):
    __tablename__ = "session_result_deliveries"
    __table_args__ = (
        UniqueConstraint("session_id", name="uq_session_result_deliveries_session_id"),
        CheckConstraint("cursor >= 0", name="result_delivery_cursor_nonnegative"),
        CheckConstraint(
            "command IN ("
            "'RESULT_NOT_STARTED', 'RESULT_PROCESSING', "
            "'RGB_SEQUENCE_READY', 'RESULT_CANCELLED'"
            ")",
            name="result_delivery_command",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    gateway_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("android_gateways.id"), nullable=False
    )
    command: Mapped[str] = mapped_column(Text, nullable=False)
    cursor: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default=text("0"))
    active_sequence_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rgb_sequences.id"), nullable=True
    )
    reason_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
