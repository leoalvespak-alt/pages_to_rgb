"""Exercise G01 migration compatibility against the documented PostgreSQL fixture."""

from __future__ import annotations

import asyncio
import os
import sys
import uuid

from sqlalchemy import text

from src.pages_to_audio.db.engine import get_engine

TAG = os.environ.get("G01_FIXTURE_TAG", "")
if not TAG:
    raise SystemExit("G01_FIXTURE_TAG is required")

DEVICE_CODE = f"G01-LIVE-{TAG}"
GATEWAY_CODE = f"G01-LIVE-{TAG}"
SESSION_PUBLIC_ID = f"G01-LIVE-{TAG}"
CAPTURE_PUBLIC_ID = f"G01-CAPTURE-{TAG}"

COUNT_QUERIES = {
    "sessions": text("select count(*) from sessions"),
    "captures": text("select count(*) from captures"),
    "frames": text("select count(*) from frames"),
    "camera_profile_revisions": text("select count(*) from camera_profile_revisions"),
    "rgb_device_commands": text("select count(*) from rgb_device_commands"),
    "rgb_device_command_events": text("select count(*) from rgb_device_command_events"),
}

FIXTURE_QUERIES = {
    "devices": text("select count(*) from devices where device_code = :value"),
    "android_gateways": text("select count(*) from android_gateways where gateway_code = :value"),
    "sessions": text("select count(*) from sessions where public_id = :value"),
    "captures": text("select count(*) from captures where capture_id = :value"),
    "frames": text("select count(*) from frames where storage_key = :value"),
}

FIXTURE_VALUES = {
    "devices": DEVICE_CODE,
    "android_gateways": GATEWAY_CODE,
    "sessions": SESSION_PUBLIC_ID,
    "captures": CAPTURE_PUBLIC_ID,
    "frames": f"g01/live/{TAG}.jpg",
}


async def _count(connection, table: str) -> int:
    return int((await connection.execute(COUNT_QUERIES[table])).scalar_one())


async def seed() -> None:
    engine = get_engine()
    ids = {name: uuid.uuid4() for name in ("device", "gateway", "session", "capture", "frame")}
    async with engine.begin() as connection:
        version = (
            await connection.execute(text("select version_num from alembic_version"))
        ).scalar_one()
        if version != "0013":
            raise RuntimeError(f"expected 0013 before seed, got {version}")
        for table in (
            "sessions",
            "captures",
            "frames",
            "camera_profile_revisions",
            "rgb_device_commands",
            "rgb_device_command_events",
        ):
            count = await _count(connection, table)
            print(f"empty {table}={count}")
            if count:
                raise RuntimeError(f"expected empty fixture table {table}, got {count}")

        await connection.execute(
            text(
                "insert into devices (id, device_code, display_name, enabled) "
                "values (:id, :device_code, :display_name, true)"
            ),
            {
                "id": ids["device"],
                "device_code": DEVICE_CODE,
                "display_name": "G01 migration fixture",
            },
        )
        await connection.execute(
            text(
                "insert into android_gateways (id, gateway_code, enabled) "
                "values (:id, :gateway_code, true)"
            ),
            {"id": ids["gateway"], "gateway_code": GATEWAY_CODE},
        )
        await connection.execute(
            text(
                "insert into sessions "
                "(id, public_id, device_id, gateway_id, status, expected_pages, "
                "expected_questions, minimum_ratio) "
                "values (:id, :public_id, :device_id, :gateway_id, :status, 1, 1, 0.8)"
            ),
            {
                "id": ids["session"],
                "public_id": SESSION_PUBLIC_ID,
                "device_id": ids["device"],
                "gateway_id": ids["gateway"],
                "status": "CAPTURING",
            },
        )
        await connection.execute(
            text(
                "insert into captures "
                "(id, session_id, capture_id, mode, status, requested_frames, received_frames) "
                "values (:id, :session_id, :capture_id, :mode, :status, 2, 1)"
            ),
            {
                "id": ids["capture"],
                "session_id": ids["session"],
                "capture_id": CAPTURE_PUBLIC_ID,
                "mode": "OCR",
                "status": "open",
            },
        )
        await connection.execute(
            text(
                "insert into frames "
                "(id, session_id, capture_id, frame_index, sha256, storage_key, mime_type) "
                "values (:id, :session_id, :capture_id, 0, :sha256, :storage_key, :mime_type)"
            ),
            {
                "id": ids["frame"],
                "session_id": ids["session"],
                "capture_id": ids["capture"],
                "sha256": "a" * 64,
                "storage_key": f"g01/live/{TAG}.jpg",
                "mime_type": "image/jpeg",
            },
        )
        print("seeded representative rows")
        print(f"fixture_tag={TAG}")
    await engine.dispose()


async def verify_old_rows(expected_version: str) -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        version = (
            await connection.execute(text("select version_num from alembic_version"))
        ).scalar_one()
        print(f"version={version}")
        if version != expected_version:
            raise RuntimeError(f"expected {expected_version}, got {version}")
        for table in ("devices", "android_gateways", "sessions", "captures", "frames"):
            count = int(
                (
                    await connection.execute(
                        FIXTURE_QUERIES[table],
                        {"value": FIXTURE_VALUES[table]},
                    )
                ).scalar_one()
            )
            print(f"fixture {table}={count}")
            if count != 1:
                raise RuntimeError(f"expected one fixture row in {table}, got {count}")
    await engine.dispose()


async def verify_new_schema() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        version = (
            await connection.execute(text("select version_num from alembic_version"))
        ).scalar_one()
        print(f"version={version}")
        if version != "0013":
            raise RuntimeError(f"expected 0013, got {version}")
        columns = {
            row[0]
            for row in (
                await connection.execute(
                    text(
                        "select table_name || '.' || column_name "
                        "from information_schema.columns "
                        "where table_schema = 'public' and table_name in "
                        "('camera_profile_revisions','rgb_device_commands',"
                        "'rgb_device_command_events','sessions','captures','frames')"
                    )
                )
            ).all()
        }
        required = {
            "camera_profile_revisions.public_id",
            "camera_profile_revisions.technical_config_json",
            "rgb_device_commands.command_id",
            "rgb_device_commands.expires_at",
            "rgb_device_command_events.idempotency_key",
            "sessions.camera_profile_snapshot_json",
            "captures.expected_frames",
            "captures.watchdog_reset",
            "frames.jpeg_valid",
            "frames.storage_etag",
            "frames.confirmed_at",
        }
        missing = required - columns
        print(f"required_columns_missing={sorted(missing)}")
        if missing:
            raise RuntimeError(f"missing required columns: {sorted(missing)}")
    await engine.dispose()


async def verify_integrity() -> None:
    engine = get_engine()
    required_indexes = {
        "uq_frames_capture_id_frame_index",
        "uq_frames_session_sha256_capture_index",
        "ix_camera_profile_revisions_device_mode_active",
        "uq_camera_profile_revisions_global_mode_revision",
        "ix_sessions_camera_profile_revision_id",
        "ix_captures_camera_profile_revision_id",
        "ix_captures_session_page_number",
        "ix_frames_session_page_frame",
        "ix_rgb_device_commands_device_status",
        "ix_rgb_device_commands_device_expiry",
        "ix_rgb_device_command_events_command_received",
    }
    required_constraints = {
        "uq_camera_profile_revisions_public_id",
        "uq_camera_profile_revisions_device_mode_revision",
        "uq_rgb_device_commands_command_id",
        "uq_rgb_device_command_events_command_idempotency",
        "ck_rgb_device_commands_ck_rgb_device_commands_duration",
    }
    async with engine.connect() as connection:
        indexes = {
            row[0]
            for row in (
                await connection.execute(
                    text("select indexname from pg_indexes where schemaname = 'public'")
                )
            ).all()
        }
        constraints = {
            row[0]
            for row in (
                await connection.execute(
                    text(
                        "select conname from pg_constraint "
                        "where connamespace = 'public'::regnamespace"
                    )
                )
            ).all()
        }
        missing_indexes = required_indexes - indexes
        missing_constraints = required_constraints - constraints
        print(f"required_indexes_missing={sorted(missing_indexes)}")
        print(f"required_constraints_missing={sorted(missing_constraints)}")
        if missing_indexes or missing_constraints:
            raise RuntimeError(
                f"missing indexes={sorted(missing_indexes)} "
                f"constraints={sorted(missing_constraints)}"
            )
    await engine.dispose()


async def verify_clean() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        version = (
            await connection.execute(text("select version_num from alembic_version"))
        ).scalar_one()
        print(f"version={version}")
        if version != "0013":
            raise RuntimeError(f"expected 0013, got {version}")
        for table in COUNT_QUERIES:
            count = await _count(connection, table)
            print(f"clean {table}={count}")
            if count:
                raise RuntimeError(f"fixture database is not clean: {table}={count}")
    await engine.dispose()


async def cleanup() -> None:
    engine = get_engine()
    async with engine.begin() as connection:
        await connection.execute(
            text("delete from frames where storage_key = :storage_key"),
            {"storage_key": f"g01/live/{TAG}.jpg"},
        )
        await connection.execute(
            text("delete from captures where capture_id = :capture_id"),
            {"capture_id": CAPTURE_PUBLIC_ID},
        )
        await connection.execute(
            text("delete from sessions where public_id = :public_id"),
            {"public_id": SESSION_PUBLIC_ID},
        )
        await connection.execute(
            text("delete from devices where device_code = :device_code"),
            {"device_code": DEVICE_CODE},
        )
        await connection.execute(
            text("delete from android_gateways where gateway_code = :gateway_code"),
            {"gateway_code": GATEWAY_CODE},
        )
        print("fixture cleanup complete")
    await engine.dispose()


async def main() -> None:
    action = sys.argv[1] if len(sys.argv) == 2 else ""
    if action == "seed":
        await seed()
    elif action == "verify-old":
        await verify_old_rows("0012")
    elif action == "verify-new":
        await verify_new_schema()
        await verify_old_rows("0013")
    elif action == "verify-integrity":
        await verify_integrity()
    elif action == "verify-clean":
        await verify_clean()
    elif action == "cleanup":
        await cleanup()
    else:
        raise SystemExit(
            "usage: g01_live_migration_fixture.py "
            "seed|verify-old|verify-new|verify-integrity|verify-clean|cleanup"
        )


asyncio.run(main())
