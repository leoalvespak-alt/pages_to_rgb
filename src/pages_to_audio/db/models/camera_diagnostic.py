from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base


class CameraDiagnostic(Base):
    """D01/D04 — controle de diagnóstico de câmera (namespace próprio).

    Nunca reutiliza capture_id/session_id de missão. Uma linha por tentativa
    (diagnostic_id próprio). Exclusão por dispositivo é lógica de aplicação
    (SELECT ... FOR UPDATE na linha ativa); este modelo só persiste estado.
    """

    __tablename__ = "camera_diagnostics"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('PHOTO','CLIP','PREVIEW')",
            name="ck_camera_diagnostics_mode",
        ),
        CheckConstraint(
            "status IN ('REQUESTED','ACTIVE','STOPPING','COMPLETED','FAILED','EXPIRED')",
            name="ck_camera_diagnostics_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    diagnostic_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    device_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id"), nullable=False
    )
    gateway_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("android_gateways.id"), nullable=True
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'REQUESTED'")
    )
    requested_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    effective_profile: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    origin: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ESP32_CAMERA'")
    )
    duration_limit_s: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("60")
    )
    bytes_limit: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("20971520")
    )
    max_frames: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    received_frames: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    received_bytes: Mapped[int] = mapped_column(
        BigInteger, nullable=False, server_default=text("0")
    )
    last_frame_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_frame_sha256: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_frame_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_frame_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    clip_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    clip_duration_s: Mapped[float | None] = mapped_column(nullable=True)
    clip_fps: Mapped[float | None] = mapped_column(nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )


class CameraDiagnosticFrame(Base):
    """D01/D04/D05 — frames de diagnóstico (fotos, clipes, prévia persistente mínima).

    Prévia transitória usa a mesma tabela com `transient=true`; a limpeza de
    10 min remove objetos + linhas transitórias, exceto a apontada por
    CameraDiagnostic.last_frame_key enquanto válida.
    """

    __tablename__ = "camera_diagnostic_frames"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    diagnostic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("camera_diagnostics.id"), nullable=False
    )
    frame_index: Mapped[int] = mapped_column(Integer, nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sha256: Mapped[str] = mapped_column(Text, nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    bytes_: Mapped[int] = mapped_column("bytes", BigInteger, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    captured_mono_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    received_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    transient: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
