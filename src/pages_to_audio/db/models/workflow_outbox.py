"""S02.9 — outbox de despacho de workflow (fechamento transacional)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class WorkflowOutbox(Base):
    """Intenção de processamento gravada na MESMA transação do LOCK.

    Dispatcher envia com workflow_id determinístico process-exam-{public_id};
    retry observável; AlreadyStarted é idempotente.
    """

    __tablename__ = "workflow_outbox"
    __table_args__ = ()

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False, unique=True
    )
    workflow_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    attempts: Mapped[int] = mapped_column(nullable=False, server_default=text("0"))
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    dispatched_at: Mapped[datetime | None] = mapped_column(nullable=True)
