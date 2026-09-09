"""D01 — tabelas de diagnóstico de câmera (namespace próprio, aditivo).

Nunca edita migrations aplicadas; apenas adiciona tabelas novas.
Revision ID: 0012
Revises: 0011
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_diagnostics",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("diagnostic_id", sa.Text(), nullable=False),
        sa.Column("device_id", sa.Uuid(), nullable=False),
        sa.Column("gateway_id", sa.Uuid(), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'REQUESTED'"), nullable=False),
        sa.Column("requested_profile", sa.JSON(), nullable=True),
        sa.Column("effective_profile", sa.JSON(), nullable=True),
        sa.Column("origin", sa.Text(), server_default=sa.text("'ESP32_CAMERA'"), nullable=False),
        sa.Column("duration_limit_s", sa.Integer(), server_default=sa.text("60"), nullable=False),
        sa.Column("bytes_limit", sa.BigInteger(), server_default=sa.text("20971520"), nullable=False),
        sa.Column("max_frames", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("received_frames", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("received_bytes", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_frame_index", sa.Integer(), nullable=True),
        sa.Column("last_frame_sha256", sa.Text(), nullable=True),
        sa.Column("last_frame_key", sa.Text(), nullable=True),
        sa.Column("last_frame_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sequence", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("clip_key", sa.Text(), nullable=True),
        sa.Column("clip_duration_s", sa.Float(), nullable=True),
        sa.Column("clip_fps", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"]),
        sa.ForeignKeyConstraint(["gateway_id"], ["android_gateways.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("diagnostic_id"),
        sa.CheckConstraint("mode IN ('PHOTO','CLIP','PREVIEW')", name="ck_camera_diagnostics_mode"),
        sa.CheckConstraint(
            "status IN ('REQUESTED','ACTIVE','STOPPING','COMPLETED','FAILED','EXPIRED')",
            name="ck_camera_diagnostics_status",
        ),
    )
    op.create_index(
        "ix_camera_diagnostics_device_status", "camera_diagnostics", ["device_id", "status"]
    )
    op.create_index("ix_camera_diagnostics_expires", "camera_diagnostics", ["expires_at"])
    op.create_table(
        "camera_diagnostic_frames",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("diagnostic_id", sa.Uuid(), nullable=False),
        sa.Column("frame_index", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("captured_mono_ms", sa.BigInteger(), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("transient", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["diagnostic_id"], ["camera_diagnostics.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("diagnostic_id", "frame_index", "sha256"),
    )
    op.create_index(
        "ix_camera_diag_frames_diag_idx", "camera_diagnostic_frames", ["diagnostic_id", "frame_index"]
    )


def downgrade() -> None:
    op.drop_index("ix_camera_diag_frames_diag_idx", table_name="camera_diagnostic_frames")
    op.drop_table("camera_diagnostic_frames")
    op.drop_index("ix_camera_diagnostics_expires", table_name="camera_diagnostics")
    op.drop_index("ix_camera_diagnostics_device_status", table_name="camera_diagnostics")
    op.drop_table("camera_diagnostics")
