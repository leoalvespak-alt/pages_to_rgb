"""Add capture_source Android/ESP32 and frame orientation metadata."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE devices ADD COLUMN capture_source TEXT NOT NULL "
        "DEFAULT 'ESP32_CAMERA' CHECK (capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA'))"
    )
    op.execute(
        "ALTER TABLE sessions ADD COLUMN capture_source TEXT NOT NULL "
        "DEFAULT 'ANDROID_CAMERA' CHECK (capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA'))"
    )
    op.execute(
        "ALTER TABLE captures ADD COLUMN capture_source TEXT NOT NULL "
        "DEFAULT 'ANDROID_CAMERA' CHECK (capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA'))"
    )
    op.execute(
        "ALTER TABLE frames ADD COLUMN capture_source TEXT NOT NULL "
        "DEFAULT 'ANDROID_CAMERA' CHECK (capture_source IN ('ANDROID_CAMERA','ESP32_CAMERA'))"
    )
    op.create_index("ix_sessions_capture_source", "sessions", ["capture_source"])
    op.execute("ALTER TABLE frames ADD COLUMN android_orientation INTEGER")
    op.execute("ALTER TABLE frames ADD COLUMN source_resolution TEXT")


def downgrade() -> None:
    op.drop_index("ix_sessions_capture_source", table_name="sessions")
    op.execute("ALTER TABLE frames DROP COLUMN IF EXISTS source_resolution")
    op.execute("ALTER TABLE frames DROP COLUMN IF EXISTS android_orientation")
    op.execute("ALTER TABLE frames DROP COLUMN IF EXISTS capture_source")
    op.execute("ALTER TABLE captures DROP COLUMN IF EXISTS capture_source")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS capture_source")
    op.execute("ALTER TABLE devices DROP COLUMN IF EXISTS capture_source")
