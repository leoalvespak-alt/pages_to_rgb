from __future__ import annotations

import uuid

from sqlalchemy import DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import mapped_column


class UUIDPk:
    """Reusable UUID primary key column."""

    @staticmethod
    def column() -> mapped_column:  # type: ignore[type-arg]
        return mapped_column(
            UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
            server_default=text("gen_random_uuid()"),
        )


class TimestampTZ:
    """Reusable TIMESTAMPTZ column with server_default=now()."""

    @staticmethod
    def created() -> mapped_column:  # type: ignore[type-arg]
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        )

    @staticmethod
    def updated() -> mapped_column:  # type: ignore[type-arg]
        return mapped_column(
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        )

    @staticmethod
    def nullable() -> mapped_column:  # type: ignore[type-arg]
        return mapped_column(DateTime(timezone=True), nullable=True)


Sha256Char = String(64)
