"""S02.8 — comandos gateway persistentes com ACK de efeito durável."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, BigInteger, ForeignKey, Integer, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class GatewayCommand(Base):
    """Um comando por (sessão, cursor). GET nunca avança sem persistir; ACK confirma efeito."""

    __tablename__ = "gateway_commands"
    __table_args__ = (
        UniqueConstraint("session_id", "cursor", name="uq_gateway_commands_session_cursor"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False
    )
    cursor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    command: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    ack_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
