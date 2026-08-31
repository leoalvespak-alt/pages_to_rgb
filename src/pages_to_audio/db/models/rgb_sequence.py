from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CHAR,
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


class RgbSequence(Base):
    __tablename__ = "rgb_sequences"
    __table_args__ = (
        UniqueConstraint("session_id", "revision", name="uq_rgb_sequences_session_revision"),
        CheckConstraint("item_count BETWEEN 1 AND 1000", name="rgb_item_count_range"),
        CheckConstraint("payload_size = item_count * 13", name="rgb_payload_size"),
        CheckConstraint("last_next_index BETWEEN 0 AND item_count", name="rgb_next_index_range"),
        CheckConstraint("schema_version = 1", name="rgb_schema_version"),
        CheckConstraint("length(sequence_id) BETWEEN 1 AND 64", name="rgb_sequence_id_length"),
        CheckConstraint("length(payload_sha256) = 64", name="rgb_sha256_length"),
        CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="rgb_sha256_format",
        ),
        CheckConstraint("answers ~ '^[A-E]+$'", name="rgb_answers_alphabet"),
        CheckConstraint("length(answers) = item_count", name="rgb_answers_count"),
        Index("ix_rgb_sequences_session_status", "session_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    sequence_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    answers: Mapped[str] = mapped_column(Text, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    defaults: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    palette: Mapped[dict[str, dict[str, object]]] = mapped_column(JSONB, nullable=False)
    overrides: Mapped[list[dict[str, object]]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )
    payload_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    payload_size: Mapped[int] = mapped_column(Integer, nullable=False)
    last_next_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    ready_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
