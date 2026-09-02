"""Make the active AI policy Google Document AI + Gemini only.

Legacy DeepSeek/Claude/GLM ciphertext columns remain nullable for backwards
compatible rollback, but no new session may select those providers.

Revision ID: 0010
Revises: 0009
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE admin_settings "
            "SET ocr_provider = 'google_document_ai', "
            "solve_model = 'gemini-3.1-pro-preview', "
            "verify_model = 'gemini-3.1-pro-preview', "
            "arbiter_model = 'gemini-3.1-pro-preview'"
        )
    )


def downgrade() -> None:
    # Values are intentionally left on Gemini.  Restoring retired model IDs
    # would make a rollback select providers that are no longer supported.
    pass

