from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class Frame(Base):
    __tablename__ = "frames"
    __table_args__ = (
        UniqueConstraint("capture_id", "frame_index", name="uq_frames_capture_id_frame_index"),
        UniqueConstraint(
            "session_id",
            "sha256",
            "capture_id",
            "frame_index",
            name="uq_frames_session_id_sha256_capture_id_frame_index",
        ),
        Index("ix_frames_session_id", "session_id"),
        CheckConstraint(
            "capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA')",
            name="ck_frames_capture_source",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    capture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("captures.id"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_length: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str] = mapped_column(Text, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    received_android_at: Mapped[datetime | None] = mapped_column(nullable=True)
    received_server_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    quality_metrics: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="accepted")
    late_upload: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    capture_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ANDROID_CAMERA'")
    )
    android_orientation: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
