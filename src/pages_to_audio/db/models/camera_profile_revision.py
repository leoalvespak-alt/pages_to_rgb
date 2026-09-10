from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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


class CameraProfileRevision(Base):
    """Versioned, immutable camera configuration used by new sessions."""

    __tablename__ = "camera_profile_revisions"
    __table_args__ = (
        UniqueConstraint("public_id", name="uq_camera_profile_revisions_public_id"),
        UniqueConstraint(
            "device_id",
            "mode",
            "revision",
            name="uq_camera_profile_revisions_device_mode_revision",
        ),
        CheckConstraint("mode IN ('OCR','PHOTO')", name="ck_camera_profile_revisions_mode"),
        CheckConstraint("revision >= 1", name="ck_camera_profile_revisions_revision"),
        CheckConstraint("frame_size = 'UXGA'", name="ck_camera_profile_revisions_frame_size"),
        CheckConstraint(
            "esp_jpeg_quality BETWEEN 8 AND 12",
            name="ck_camera_profile_revisions_esp_jpeg_quality",
        ),
        CheckConstraint(
            "frame_count BETWEEN 1 AND 3",
            name="ck_camera_profile_revisions_frame_count",
        ),
        CheckConstraint(
            "intra_frame_gap_ms BETWEEN 180 AND 300",
            name="ck_camera_profile_revisions_intra_frame_gap",
        ),
        CheckConstraint(
            "page_interval_ms >= 5000",
            name="ck_camera_profile_revisions_page_interval",
        ),
        Index(
            "ix_camera_profile_revisions_device_mode_active",
            "device_id",
            "mode",
            "active",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    public_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, server_default=text("gen_random_uuid()")
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("devices.id", ondelete="RESTRICT"), nullable=True
    )
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_size: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'UXGA'"))
    esp_jpeg_quality: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("10")
    )
    frame_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("2"))
    intra_frame_gap_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("220")
    )
    page_interval_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5000")
    )
    brightness: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    contrast: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    saturation: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    awb: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    awb_gain: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    wb_mode: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'AUTO'"))
    aec: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    aec2: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    agc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    bpc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    wpc: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    raw_gamma: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    lens_correction: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    dcw: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    hmirror: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    vflip: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    special_effect: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'NORMAL'")
    )
    colorbar: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    technical_config_json: Mapped[dict[str, object]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    capabilities_version: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'v2'")
    )
    created_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    superseded_at: Mapped[datetime | None] = mapped_column(nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
