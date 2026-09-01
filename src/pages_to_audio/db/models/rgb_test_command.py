from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Integer, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class RgbTestCommand(Base):
    __tablename__ = "rgb_test_commands"
    __table_args__ = (
        CheckConstraint("brightness_percent BETWEEN 0 AND 100", name="ck_rgb_test_brightness"),
        CheckConstraint("on_ms BETWEEN 100 AND 60000", name="ck_rgb_test_on_ms"),
        CheckConstraint("off_ms BETWEEN 0 AND 60000", name="ck_rgb_test_off_ms"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rgb: Mapped[list[int]] = mapped_column(JSONB, nullable=False)
    brightness_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    on_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    off_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    delivered_at: Mapped[datetime | None] = mapped_column(nullable=True)
