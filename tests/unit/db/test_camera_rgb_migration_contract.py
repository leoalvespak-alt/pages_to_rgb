from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from src.pages_to_audio.db.base import Base
from src.pages_to_audio.db.models import (
    CameraProfileRevision,
    RgbDeviceCommand,
    RgbDeviceCommandEvent,
)

MIGRATION = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "0013_camera_profiles_rgb_device_commands.py"
)


def test_g01_metadata_keeps_legacy_tables_and_adds_required_rgb_tables():
    expected_tables = {
        "camera_profile_revisions",
        "rgb_device_commands",
        "rgb_device_command_events",
        "sessions",
        "captures",
        "frames",
        "rgb_test_commands",
    }

    assert expected_tables <= set(Base.metadata.tables)

    assert {
        "camera_profile_revision_id",
        "camera_profile_snapshot_json",
        "requested_camera_config_json",
        "effective_camera_config_json",
        "firmware_version",
        "capabilities_version",
    } <= {column.name for column in Base.metadata.tables["sessions"].columns}

    assert {
        "page_number",
        "expected_frames",
        "requested_resolution",
        "effective_resolution",
        "requested_esp_jpeg_quality",
        "effective_esp_jpeg_quality",
        "fb_overflow",
        "dma_overflow",
        "watchdog_reset",
    } <= {column.name for column in Base.metadata.tables["captures"].columns}

    assert {
        "page_number",
        "frame_number",
        "sha256",
        "jpeg_size_bytes",
        "jpeg_valid",
        "psram_free_bytes",
        "psram_largest_block_bytes",
        "storage_key_original",
        "storage_etag",
        "confirmed_at",
    } <= {column.name for column in Base.metadata.tables["frames"].columns}


def test_g01_new_tables_expose_idempotency_and_command_state_fields():
    profile_columns = {column.name for column in CameraProfileRevision.__table__.columns}
    assert {
        "public_id",
        "device_id",
        "mode",
        "revision",
        "frame_size",
        "esp_jpeg_quality",
        "technical_config_json",
        "capabilities_version",
        "active",
    } <= profile_columns

    command_columns = {column.name for column in RgbDeviceCommand.__table__.columns}
    assert {
        "command_id",
        "device_id",
        "session_id",
        "kind",
        "rgb",
        "status",
        "expires_at",
        "attempt_count",
    } <= command_columns

    event_columns = {column.name for column in RgbDeviceCommandEvent.__table__.columns}
    assert {
        "command_id",
        "event_type",
        "payload",
        "firmware_version",
        "device_timestamp",
        "idempotency_key",
    } <= event_columns

    event_fk_targets = {fk.target_fullname for fk in RgbDeviceCommandEvent.__table__.foreign_keys}
    assert "rgb_device_commands.command_id" in event_fk_targets


def test_g01_postgresql_ddl_compiles_for_empty_and_existing_schema_paths():
    dialect = postgresql.dialect()
    for table_name in (
        "camera_profile_revisions",
        "rgb_device_commands",
        "rgb_device_command_events",
    ):
        ddl = str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=dialect))
        assert f"CREATE TABLE {table_name}" in ddl

    migration = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "0013"' in migration
    assert 'down_revision = "0012"' in migration
    assert "def upgrade()" in migration
    assert "def downgrade()" in migration
    assert 'op.drop_table("rgb_test_commands")' not in migration
    assert 'op.drop_table("sessions")' not in migration
    assert 'op.drop_table("captures")' not in migration
    assert 'op.drop_table("frames")' not in migration
