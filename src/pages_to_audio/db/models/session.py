from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_sessions_public_id"),
        CheckConstraint(
            "capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA')",
            name="ck_sessions_capture_source",
        ),
        CheckConstraint(
            "session_type IN ('EXAM','HANDWRITTEN_WORD')",
            name="ck_sessions_session_type",
        ),
        Index("ix_sessions_capture_source", "capture_source"),
        Index("ix_sessions_session_type", "session_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    public_id: Mapped[str] = mapped_column(Text, nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    gateway_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("android_gateways.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(Text, nullable=False)
    expected_pages: Mapped[int] = mapped_column(Integer, nullable=False)
    expected_questions: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_ratio: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    capture_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    capture_locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    end_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    provider_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    degraded_mode: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    capture_source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ANDROID_CAMERA'")
    )
    session_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'EXAM'")
    )
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
