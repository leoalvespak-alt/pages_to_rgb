"""S03 — versioned camera persistence and auditable physical RGB commands.

This migration is additive.  Existing camera/session/frame data and the legacy
``rgb_test_commands`` table remain readable.  The downgrade removes only the
objects introduced here; application rollback must continue using the previous
schema rather than deleting historical mission data.

Revision ID: 0013
Revises: 0012
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "camera_profile_revisions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "public_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mode", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("frame_size", sa.Text(), server_default=sa.text("'UXGA'"), nullable=False),
        sa.Column("esp_jpeg_quality", sa.Integer(), server_default=sa.text("10"), nullable=False),
        sa.Column("frame_count", sa.Integer(), server_default=sa.text("2"), nullable=False),
        sa.Column(
            "intra_frame_gap_ms", sa.Integer(), server_default=sa.text("220"), nullable=False
        ),
        sa.Column("page_interval_ms", sa.Integer(), server_default=sa.text("5000"), nullable=False),
        sa.Column("brightness", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("contrast", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("saturation", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("awb", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("awb_gain", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("wb_mode", sa.Text(), server_default=sa.text("'AUTO'"), nullable=False),
        sa.Column("aec", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("aec2", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("agc", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("bpc", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("wpc", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("raw_gamma", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("lens_correction", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("dcw", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("hmirror", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("vflip", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("special_effect", sa.Text(), server_default=sa.text("'NORMAL'"), nullable=False),
        sa.Column("colorbar", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "technical_config_json",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "capabilities_version", sa.Text(), server_default=sa.text("'v2'"), nullable=False
        ),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name="fk_camera_profile_revisions_device_id_devices",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("public_id", name="uq_camera_profile_revisions_public_id"),
        sa.UniqueConstraint(
            "device_id",
            "mode",
            "revision",
            name="uq_camera_profile_revisions_device_mode_revision",
        ),
        sa.CheckConstraint("mode IN ('OCR','PHOTO')", name="ck_camera_profile_revisions_mode"),
        sa.CheckConstraint("revision >= 1", name="ck_camera_profile_revisions_revision"),
        sa.CheckConstraint("frame_size = 'UXGA'", name="ck_camera_profile_revisions_frame_size"),
        sa.CheckConstraint(
            "esp_jpeg_quality BETWEEN 8 AND 12",
            name="ck_camera_profile_revisions_esp_jpeg_quality",
        ),
        sa.CheckConstraint(
            "frame_count BETWEEN 1 AND 3", name="ck_camera_profile_revisions_frame_count"
        ),
        sa.CheckConstraint(
            "intra_frame_gap_ms BETWEEN 180 AND 300",
            name="ck_camera_profile_revisions_intra_frame_gap",
        ),
        sa.CheckConstraint(
            "page_interval_ms >= 5000",
            name="ck_camera_profile_revisions_page_interval",
        ),
    )
    op.create_index(
        "ix_camera_profile_revisions_device_mode_active",
        "camera_profile_revisions",
        ["device_id", "mode", "active"],
    )
    op.create_index(
        "uq_camera_profile_revisions_global_mode_revision",
        "camera_profile_revisions",
        ["mode", "revision"],
        unique=True,
        postgresql_where=sa.text("device_id IS NULL"),
    )

    session_columns = (
        sa.Column("camera_profile_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("camera_profile_snapshot_json", postgresql.JSONB(), nullable=True),
        sa.Column("requested_camera_config_json", postgresql.JSONB(), nullable=True),
        sa.Column("effective_camera_config_json", postgresql.JSONB(), nullable=True),
        sa.Column("firmware_version", sa.Text(), nullable=True),
        sa.Column("capabilities_version", sa.Text(), nullable=True),
    )
    for column in session_columns:
        op.add_column("sessions", column)
    op.create_foreign_key(
        "fk_sessions_camera_profile_revision_id_camera_profile_revisions",
        "sessions",
        "camera_profile_revisions",
        ["camera_profile_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_sessions_camera_profile_revision_id",
        "sessions",
        ["camera_profile_revision_id"],
    )

    capture_columns = (
        sa.Column("camera_profile_revision_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("camera_profile_snapshot_json", postgresql.JSONB(), nullable=True),
        sa.Column("requested_camera_config_json", postgresql.JSONB(), nullable=True),
        sa.Column("effective_camera_config_json", postgresql.JSONB(), nullable=True),
        sa.Column("firmware_version", sa.Text(), nullable=True),
        sa.Column("capabilities_version", sa.Text(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("requested_resolution", sa.Text(), nullable=True),
        sa.Column("effective_resolution", sa.Text(), nullable=True),
        sa.Column("requested_esp_jpeg_quality", sa.Integer(), nullable=True),
        sa.Column("effective_esp_jpeg_quality", sa.Integer(), nullable=True),
        sa.Column("configured_buffer_bytes", sa.BigInteger(), nullable=True),
        sa.Column("dma_enabled", sa.Boolean(), nullable=True),
        sa.Column("expected_frames", sa.Integer(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("capture_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("upload_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("fb_overflow", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("dma_overflow", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("watchdog_reset", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
    )
    for column in capture_columns:
        op.add_column("captures", column)
    op.create_foreign_key(
        "fk_captures_camera_profile_revision_id_camera_profile_revisions",
        "captures",
        "camera_profile_revisions",
        ["camera_profile_revision_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_captures_camera_profile_revision_id",
        "captures",
        ["camera_profile_revision_id"],
    )
    op.create_index("ix_captures_session_page_number", "captures", ["session_id", "page_number"])
    op.create_check_constraint(
        "ck_captures_page_number_nonnegative",
        "captures",
        "page_number IS NULL OR page_number >= 0",
    )
    op.create_check_constraint(
        "ck_captures_expected_frames_range",
        "captures",
        "expected_frames IS NULL OR expected_frames BETWEEN 1 AND 3",
    )
    op.create_check_constraint(
        "ck_captures_requested_esp_quality",
        "captures",
        "requested_esp_jpeg_quality IS NULL OR requested_esp_jpeg_quality BETWEEN 8 AND 12",
    )
    op.create_check_constraint(
        "ck_captures_effective_esp_quality",
        "captures",
        "effective_esp_jpeg_quality IS NULL OR effective_esp_jpeg_quality BETWEEN 8 AND 12",
    )
    op.create_check_constraint(
        "ck_captures_retry_count_nonnegative",
        "captures",
        "retry_count >= 0",
    )

    frame_columns = (
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("frame_number", sa.Integer(), nullable=True),
        sa.Column("requested_resolution", sa.Text(), nullable=True),
        sa.Column("effective_resolution", sa.Text(), nullable=True),
        sa.Column("requested_esp_jpeg_quality", sa.Integer(), nullable=True),
        sa.Column("effective_esp_jpeg_quality", sa.Integer(), nullable=True),
        sa.Column("configured_buffer_bytes", sa.BigInteger(), nullable=True),
        sa.Column("dma_enabled", sa.Boolean(), nullable=True),
        sa.Column("firmware_version", sa.Text(), nullable=True),
        sa.Column("jpeg_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("jpeg_valid", sa.Boolean(), nullable=True),
        sa.Column("psram_free_bytes", sa.BigInteger(), nullable=True),
        sa.Column("psram_largest_block_bytes", sa.BigInteger(), nullable=True),
        sa.Column("capture_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("upload_duration_ms", sa.BigInteger(), nullable=True),
        sa.Column("storage_key_original", sa.Text(), nullable=True),
        sa.Column("storage_etag", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fb_overflow", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("dma_overflow", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("watchdog_reset", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
    )
    for column in frame_columns:
        op.add_column("frames", column)
    op.create_index(
        "ix_frames_session_page_frame", "frames", ["session_id", "page_number", "frame_number"]
    )
    op.create_check_constraint(
        "ck_frames_page_number_nonnegative",
        "frames",
        "page_number IS NULL OR page_number >= 0",
    )
    op.create_check_constraint(
        "ck_frames_frame_number_nonnegative",
        "frames",
        "frame_number IS NULL OR frame_number >= 0",
    )
    op.create_check_constraint(
        "ck_frames_requested_esp_quality",
        "frames",
        "requested_esp_jpeg_quality IS NULL OR requested_esp_jpeg_quality BETWEEN 8 AND 12",
    )
    op.create_check_constraint(
        "ck_frames_effective_esp_quality",
        "frames",
        "effective_esp_jpeg_quality IS NULL OR effective_esp_jpeg_quality BETWEEN 8 AND 12",
    )
    op.create_check_constraint("ck_frames_retry_count_nonnegative", "frames", "retry_count >= 0")

    op.create_table(
        "rgb_device_commands",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "command_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("rgb", postgresql.JSONB(), nullable=False),
        sa.Column("brightness_percent", sa.Integer(), nullable=False),
        sa.Column("on_ms", sa.Integer(), nullable=False),
        sa.Column("off_ms", sa.Integer(), nullable=False),
        sa.Column("repeat_count", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.Text(), server_default=sa.text("'QUEUED'"), nullable=False),
        sa.Column(
            "queued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("forwarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name="fk_rgb_device_commands_device_id_devices",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_rgb_device_commands_session_id_sessions",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", name="uq_rgb_device_commands_command_id"),
        sa.CheckConstraint("kind IN ('TEST','STOP')", name="ck_rgb_device_commands_kind"),
        sa.CheckConstraint(
            "status IN ("
            "'QUEUED','FORWARDED','RECEIVED','APPLIED','OFF',"
            "'EXPIRED','FAILED','CANCELLED')",
            name="ck_rgb_device_commands_status",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(rgb) = 'array' AND jsonb_array_length(rgb) = 3",
            name="ck_rgb_device_commands_rgb_shape",
        ),
        sa.CheckConstraint(
            "brightness_percent BETWEEN 0 AND 100", name="ck_rgb_device_commands_brightness"
        ),
        sa.CheckConstraint("on_ms BETWEEN 100 AND 60000", name="ck_rgb_device_commands_on_ms"),
        sa.CheckConstraint("off_ms BETWEEN 0 AND 60000", name="ck_rgb_device_commands_off_ms"),
        sa.CheckConstraint(
            "repeat_count BETWEEN 1 AND 20", name="ck_rgb_device_commands_repeat_count"
        ),
        sa.CheckConstraint(
            "(on_ms + off_ms) * repeat_count <= 120000", name="ck_rgb_device_commands_duration"
        ),
        sa.CheckConstraint("attempt_count >= 0", name="ck_rgb_device_commands_attempt_count"),
    )
    op.create_index(
        "ix_rgb_device_commands_device_status", "rgb_device_commands", ["device_id", "status"]
    )
    op.create_index(
        "ix_rgb_device_commands_device_expiry", "rgb_device_commands", ["device_id", "expires_at"]
    )

    op.create_table(
        "rgb_device_command_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("command_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column("requested_payload", postgresql.JSONB(), nullable=True),
        sa.Column("effective_payload", postgresql.JSONB(), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("firmware_version", sa.Text(), nullable=True),
        sa.Column("device_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["command_id"],
            ["rgb_device_commands.command_id"],
            name="fk_rgb_device_command_events_command_id_rgb_device_commands",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"],
            ["devices.id"],
            name="fk_rgb_device_command_events_device_id_devices",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "command_id",
            "idempotency_key",
            name="uq_rgb_device_command_events_command_idempotency",
        ),
        sa.CheckConstraint(
            "event_type IN ('FORWARDED','RECEIVED','APPLIED','OFF','FAILED','EXPIRED','CANCELLED')",
            name="ck_rgb_device_command_events_type",
        ),
    )
    op.create_index(
        "ix_rgb_device_command_events_command_received",
        "rgb_device_command_events",
        ["command_id", "received_at"],
    )


def downgrade() -> None:
    """Remove only 0013 objects; legacy mission tables remain untouched."""
    op.drop_index(
        "ix_rgb_device_command_events_command_received",
        table_name="rgb_device_command_events",
    )
    op.drop_table("rgb_device_command_events")
    op.drop_index("ix_rgb_device_commands_device_expiry", table_name="rgb_device_commands")
    op.drop_index("ix_rgb_device_commands_device_status", table_name="rgb_device_commands")
    op.drop_table("rgb_device_commands")

    for name in (
        "ck_frames_retry_count_nonnegative",
        "ck_frames_effective_esp_quality",
        "ck_frames_requested_esp_quality",
        "ck_frames_frame_number_nonnegative",
        "ck_frames_page_number_nonnegative",
    ):
        op.drop_constraint(name, "frames", type_="check")
    op.drop_index("ix_frames_session_page_frame", table_name="frames")
    for name in (
        "error_code",
        "watchdog_reset",
        "dma_overflow",
        "fb_overflow",
        "confirmed_at",
        "received_at",
        "retry_count",
        "storage_etag",
        "storage_key_original",
        "upload_duration_ms",
        "capture_duration_ms",
        "psram_largest_block_bytes",
        "psram_free_bytes",
        "jpeg_valid",
        "jpeg_size_bytes",
        "firmware_version",
        "dma_enabled",
        "configured_buffer_bytes",
        "effective_esp_jpeg_quality",
        "requested_esp_jpeg_quality",
        "effective_resolution",
        "requested_resolution",
        "frame_number",
        "page_number",
    ):
        op.drop_column("frames", name)

    for name in (
        "ck_captures_retry_count_nonnegative",
        "ck_captures_effective_esp_quality",
        "ck_captures_requested_esp_quality",
        "ck_captures_expected_frames_range",
        "ck_captures_page_number_nonnegative",
    ):
        op.drop_constraint(name, "captures", type_="check")
    op.drop_index("ix_captures_session_page_number", table_name="captures")
    op.drop_index("ix_captures_camera_profile_revision_id", table_name="captures")
    op.drop_constraint(
        "fk_captures_camera_profile_revision_id_camera_profile_revisions",
        "captures",
        type_="foreignkey",
    )
    for name in (
        "error_code",
        "watchdog_reset",
        "dma_overflow",
        "fb_overflow",
        "upload_duration_ms",
        "capture_duration_ms",
        "retry_count",
        "expected_frames",
        "dma_enabled",
        "configured_buffer_bytes",
        "effective_esp_jpeg_quality",
        "requested_esp_jpeg_quality",
        "effective_resolution",
        "requested_resolution",
        "page_number",
        "capabilities_version",
        "firmware_version",
        "effective_camera_config_json",
        "requested_camera_config_json",
        "camera_profile_snapshot_json",
        "camera_profile_revision_id",
    ):
        op.drop_column("captures", name)

    op.drop_index("ix_sessions_camera_profile_revision_id", table_name="sessions")
    op.drop_constraint(
        "fk_sessions_camera_profile_revision_id_camera_profile_revisions",
        "sessions",
        type_="foreignkey",
    )
    for name in (
        "capabilities_version",
        "firmware_version",
        "effective_camera_config_json",
        "requested_camera_config_json",
        "camera_profile_snapshot_json",
        "camera_profile_revision_id",
    ):
        op.drop_column("sessions", name)

    op.drop_index(
        "uq_camera_profile_revisions_global_mode_revision",
        table_name="camera_profile_revisions",
    )
    op.drop_index(
        "ix_camera_profile_revisions_device_mode_active",
        table_name="camera_profile_revisions",
    )
    op.drop_table("camera_profile_revisions")
