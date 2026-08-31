from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class Capture(Base):
    __tablename__ = "captures"
    __table_args__ = (
        UniqueConstraint("session_id", "capture_id", name="uq_captures_session_id_capture_id"),
        CheckConstraint(
            "capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA')",
            name="ck_captures_capture_source",
        ),
        CheckConstraint(
            "session_type IN ('EXAM','HANDWRITTEN_WORD')",
            name="ck_captures_session_type",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    capture_id: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    command_cursor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    requested_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received_frames: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    capture_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ANDROID_CAMERA'")
    )
    session_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'EXAM'")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
