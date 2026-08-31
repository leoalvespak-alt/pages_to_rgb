from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Integer, Numeric, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class LogicalPage(Base):
    __tablename__ = "logical_pages"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "logical_index", name="uq_logical_pages_session_id_logical_index"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    logical_index: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_frame_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("frames.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, default="accepted")
    quality_score: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
