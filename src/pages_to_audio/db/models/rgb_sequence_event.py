from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class RgbSequenceEvent(Base):
    __tablename__ = "rgb_sequence_events"
    __table_args__ = (
        CheckConstraint("next_index >= 0", name="rgb_event_next_index_nonnegative"),
        CheckConstraint("next_index <= item_count", name="rgb_event_next_index_max"),
        CheckConstraint(
            "event IN ('RECEIVED', 'STARTED', 'RESUMED', 'COMPLETED', 'INVALID')",
            name="rgb_event_name",
        ),
        CheckConstraint("item_count BETWEEN 1 AND 1000", name="rgb_event_item_count"),
        Index("ix_rgb_sequence_events_sequence_received", "rgb_sequence_id", "received_at"),
        Index(
            "ix_rgb_sequence_events_gateway_idempotency",
            "gateway_id",
            "idempotency_key",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    rgb_sequence_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rgb_sequences.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    gateway_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("android_gateways.id"), nullable=False
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)
    next_index: Mapped[int] = mapped_column(Integer, nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_identity: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
