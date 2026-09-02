"""Add context columns expected by the audit event model.

Revision ID: 0008
Revises: 0007
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_events",
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("frame_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "audit_events",
        sa.Column("capture_id", postgresql.UUID(as_uuid=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("audit_events", "capture_id")
    op.drop_column("audit_events", "frame_id")
    op.drop_column("audit_events", "question_id")
