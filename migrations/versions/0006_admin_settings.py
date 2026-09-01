"""Add secure singleton admin settings.

Revision ID: 0006
Revises: 0005
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


EXAM_PALETTE = {
    "A": {"rgb": [255, 255, 255]},
    "B": {"rgb": [255, 255, 0]},
    "C": {"rgb": [0, 255, 255]},
    "D": {"rgb": [0, 0, 255]},
    "E": {"rgb": [255, 0, 0]},
}
HANDWRITTEN_PALETTE = {
    "A": {"rgb": [0, 0, 255]},
    "B": {"rgb": [255, 0, 0]},
    "C": {"rgb": [0, 255, 0]},
    "D": {"rgb": [128, 0, 128]},
    "E": {"rgb": [255, 255, 0]},
}


def upgrade() -> None:
    op.create_table(
        "admin_settings",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            primary_key=True,
        ),
        sa.Column("singleton_key", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("ocr_provider", sa.Text(), server_default="google_document_ai", nullable=False),
        sa.Column("solve_model", sa.Text(), server_default="deepseek-v4-pro", nullable=False),
        sa.Column("verify_model", sa.Text(), server_default="deepseek-v4-pro", nullable=False),
        sa.Column("arbiter_model", sa.Text(), server_default="claude-opus-5", nullable=False),
        sa.Column("deepseek_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("gemini_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("anthropic_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("glm_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("secrets_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("expected_pages", sa.Integer(), server_default="30", nullable=False),
        sa.Column("expected_questions", sa.Integer(), server_default="70", nullable=False),
        sa.Column(
            "handwritten_expected_questions", sa.Integer(), server_default="10", nullable=False
        ),
        sa.Column("minimum_ratio", sa.Numeric(5, 4), server_default="0.9000", nullable=False),
        sa.Column("brightness_percent", sa.Integer(), server_default="12", nullable=False),
        sa.Column("on_ms", sa.Integer(), server_default="3000", nullable=False),
        sa.Column("off_ms", sa.Integer(), server_default="5000", nullable=False),
        sa.Column("palette", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("handwritten_palette", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("singleton_key = 1", name="ck_admin_settings_singleton"),
        sa.CheckConstraint("expected_pages BETWEEN 1 AND 1000", name="ck_admin_expected_pages"),
        sa.CheckConstraint(
            "expected_questions BETWEEN 1 AND 1000", name="ck_admin_expected_questions"
        ),
        sa.CheckConstraint(
            "handwritten_expected_questions BETWEEN 1 AND 1000",
            name="ck_admin_handwritten_expected_questions",
        ),
        sa.CheckConstraint("minimum_ratio > 0 AND minimum_ratio <= 1", name="ck_admin_min_ratio"),
        sa.CheckConstraint("brightness_percent BETWEEN 0 AND 100", name="ck_admin_brightness"),
        sa.CheckConstraint("on_ms BETWEEN 100 AND 60000", name="ck_admin_on_ms"),
        sa.CheckConstraint("off_ms BETWEEN 0 AND 60000", name="ck_admin_off_ms"),
        sa.UniqueConstraint("singleton_key", name="uq_admin_settings_singleton_key"),
    )
    op.execute(
        sa.text(
            "INSERT INTO admin_settings (singleton_key, palette, handwritten_palette) "
            "VALUES (1, CAST(:palette AS jsonb), CAST(:handwritten AS jsonb)) "
            "ON CONFLICT (singleton_key) DO NOTHING"
        ).bindparams(palette=json.dumps(EXAM_PALETTE), handwritten=json.dumps(HANDWRITTEN_PALETTE))
    )


def downgrade() -> None:
    op.drop_table("admin_settings")
