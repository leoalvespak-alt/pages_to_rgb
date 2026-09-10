from __future__ import annotations

import os

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_schema_is_migrated_to_rgb_contract():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration tests")

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            assert revision == "0013"

            result = await connection.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' "
                    "AND tablename IN ("
                    "'camera_profile_revisions', "
                    "'rgb_device_commands', "
                    "'rgb_device_command_events'"
                    ")"
                )
            )
            assert {row[0] for row in result} == {
                "camera_profile_revisions",
                "rgb_device_commands",
                "rgb_device_command_events",
            }
    finally:
        await engine.dispose()
