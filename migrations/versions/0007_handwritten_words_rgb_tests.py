"""Add configurable handwritten words and RGB test commands.

Revision ID: 0007
Revises: 0006
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


DEFAULT_WORDS = {"A": "João", "B": "Maria", "C": "Pedro", "D": "Paula", "E": "Fernanda"}


def upgrade() -> None:
    op.add_column(
        "admin_settings",
        sa.Column(
            "handwritten_words",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text(f"'{json.dumps(DEFAULT_WORDS, ensure_ascii=False)}'::jsonb"),
            nullable=False,
        ),
    )
    op.create_table(
        "rgb_test_commands",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rgb", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("brightness_percent", sa.Integer(), nullable=False),
        sa.Column("on_ms", sa.Integer(), nullable=False),
        sa.Column("off_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("public_id", name="uq_rgb_test_commands_public_id"),
        sa.CheckConstraint("brightness_percent BETWEEN 0 AND 100", name="ck_rgb_test_brightness"),
        sa.CheckConstraint("on_ms BETWEEN 100 AND 60000", name="ck_rgb_test_on_ms"),
        sa.CheckConstraint("off_ms BETWEEN 0 AND 60000", name="ck_rgb_test_off_ms"),
    )
    op.create_index("ix_rgb_test_commands_session_id", "rgb_test_commands", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_rgb_test_commands_session_id", table_name="rgb_test_commands")
    op.drop_table("rgb_test_commands")
    op.drop_column("admin_settings", "handwritten_words")
