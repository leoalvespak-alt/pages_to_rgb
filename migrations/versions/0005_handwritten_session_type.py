"""Add session_type EXAM/HANDWRITTEN_WORD for alternative flow."""

from __future__ import annotations

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE sessions ADD COLUMN session_type TEXT NOT NULL "
        "DEFAULT 'EXAM' CHECK (session_type IN ('EXAM','HANDWRITTEN_WORD'))"
    )
    op.execute(
        "ALTER TABLE captures ADD COLUMN session_type TEXT NOT NULL "
        "DEFAULT 'EXAM' CHECK (session_type IN ('EXAM','HANDWRITTEN_WORD'))"
    )
    op.create_index("ix_sessions_session_type", "sessions", ["session_type"])


def downgrade() -> None:
    op.drop_index("ix_sessions_session_type", table_name="sessions")
    op.execute("ALTER TABLE captures DROP COLUMN IF EXISTS session_type")
    op.execute("ALTER TABLE sessions DROP COLUMN IF EXISTS session_type")
