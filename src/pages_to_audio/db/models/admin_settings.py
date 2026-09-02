from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Integer, Numeric, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.pages_to_audio.db.base import Base

DEFAULT_EXAM_PALETTE = {
    "A": {"rgb": [255, 255, 255]},
    "B": {"rgb": [255, 255, 0]},
    "C": {"rgb": [0, 255, 255]},
    "D": {"rgb": [0, 0, 255]},
    "E": {"rgb": [255, 0, 0]},
}
DEFAULT_HANDWRITTEN_PALETTE = {
    "A": {"rgb": [0, 0, 255]},
    "B": {"rgb": [255, 0, 0]},
    "C": {"rgb": [0, 255, 0]},
    "D": {"rgb": [128, 0, 128]},
    "E": {"rgb": [255, 255, 0]},
}
DEFAULT_HANDWRITTEN_WORDS = {
    "A": "João",
    "B": "Maria",
    "C": "Pedro",
    "D": "Paula",
    "E": "Fernanda",
}


class AdminSettings(Base):
    __tablename__ = "admin_settings"
    __table_args__ = (
        CheckConstraint("singleton_key = 1", name="ck_admin_settings_singleton"),
        CheckConstraint("expected_pages BETWEEN 1 AND 1000", name="ck_admin_expected_pages"),
        CheckConstraint(
            "expected_questions BETWEEN 1 AND 1000", name="ck_admin_expected_questions"
        ),
        CheckConstraint(
            "handwritten_expected_questions BETWEEN 1 AND 1000",
            name="ck_admin_handwritten_expected_questions",
        ),
        CheckConstraint("minimum_ratio > 0 AND minimum_ratio <= 1", name="ck_admin_min_ratio"),
        CheckConstraint("brightness_percent BETWEEN 0 AND 100", name="ck_admin_brightness"),
        CheckConstraint("on_ms BETWEEN 100 AND 60000", name="ck_admin_on_ms"),
        CheckConstraint("off_ms BETWEEN 0 AND 60000", name="ck_admin_off_ms"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    singleton_key: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, unique=True, server_default=text("1")
    )
    ocr_provider: Mapped[str] = mapped_column(Text, nullable=False, default="google_document_ai")
    solve_model: Mapped[str] = mapped_column(
        Text, nullable=False, default="gemini-3.1-pro-preview"
    )
    verify_model: Mapped[str] = mapped_column(
        Text, nullable=False, default="gemini-3.1-pro-preview"
    )
    arbiter_model: Mapped[str] = mapped_column(
        Text, nullable=False, default="gemini-3.1-pro-preview"
    )
    deepseek_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    gemini_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    anthropic_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    glm_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Google Document AI is a separate credential/configuration from Gemini.
    google_document_ai_project_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_document_ai_location: Mapped[str] = mapped_column(
        Text, nullable=False, default="us", server_default="us"
    )
    google_document_ai_processor_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_document_ai_processor_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    google_document_ai_credentials_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    secrets_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expected_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    expected_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    handwritten_expected_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    minimum_ratio: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, default=Decimal("0.9000")
    )
    brightness_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    on_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=3000)
    off_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=5000)
    palette: Mapped[dict[str, dict[str, list[int]]]] = mapped_column(
        JSONB, nullable=False, default=lambda: DEFAULT_EXAM_PALETTE.copy()
    )
    handwritten_palette: Mapped[dict[str, dict[str, list[int]]]] = mapped_column(
        JSONB, nullable=False, default=lambda: DEFAULT_HANDWRITTEN_PALETTE.copy()
    )
    handwritten_words: Mapped[dict[str, str]] = mapped_column(
        JSONB, nullable=False, default=lambda: DEFAULT_HANDWRITTEN_WORDS.copy()
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )
