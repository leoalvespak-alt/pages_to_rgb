"""Store Google Document AI configuration separately from Gemini credentials.

Revision ID: 0009
Revises: 0008
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("admin_settings", sa.Column("google_document_ai_project_id", sa.Text()))
    op.add_column(
        "admin_settings",
        sa.Column("google_document_ai_location", sa.Text(), nullable=False, server_default="us"),
    )
    op.add_column("admin_settings", sa.Column("google_document_ai_processor_id", sa.Text()))
    op.add_column(
        "admin_settings", sa.Column("google_document_ai_processor_version", sa.Text())
    )
    op.add_column(
        "admin_settings",
        sa.Column("google_document_ai_credentials_encrypted", sa.Text()),
    )


def downgrade() -> None:
    op.drop_column("admin_settings", "google_document_ai_credentials_encrypted")
    op.drop_column("admin_settings", "google_document_ai_processor_version")
    op.drop_column("admin_settings", "google_document_ai_processor_id")
    op.drop_column("admin_settings", "google_document_ai_location")
    op.drop_column("admin_settings", "google_document_ai_project_id")

