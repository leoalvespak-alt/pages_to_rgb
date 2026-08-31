"""Add durable firmware V2.2 RGB result delivery state."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The ORM models already require these metadata columns, while the
    # original bootstrap migration predates them. This forward-only migration
    # brings the live schema in line without editing an applied migration.
    op.add_column(
        "devices",
        sa.Column("display_name", sa.Text(), nullable=False, server_default=sa.text("''")),
    )
    op.add_column("devices", sa.Column("firmware_version", sa.Text(), nullable=True))
    op.add_column("devices", sa.Column("metadata", postgresql.JSONB(), nullable=True))
    op.add_column("devices", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("android_gateways", sa.Column("app_version", sa.Text(), nullable=True))
    op.add_column("android_gateways", sa.Column("device_model", sa.Text(), nullable=True))
    op.add_column("android_gateways", sa.Column("metadata", postgresql.JSONB(), nullable=True))

    op.create_table(
        "rgb_sequences",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("sequence_id", sa.Text(), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("answers", sa.Text(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("defaults", postgresql.JSONB(), nullable=False),
        sa.Column("palette", postgresql.JSONB(), nullable=False),
        sa.Column(
            "overrides",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("payload_sha256", sa.CHAR(64), nullable=False),
        sa.Column("payload_size", sa.Integer(), nullable=False),
        sa.Column("last_next_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rgb_sequences"),
        sa.UniqueConstraint("sequence_id", name="uq_rgb_sequences_sequence_id"),
        sa.UniqueConstraint("session_id", "revision", name="uq_rgb_sequences_session_revision"),
        sa.CheckConstraint("item_count BETWEEN 1 AND 1000", name="rgb_item_count_range"),
        sa.CheckConstraint("payload_size = item_count * 13", name="rgb_payload_size"),
        sa.CheckConstraint("last_next_index BETWEEN 0 AND item_count", name="rgb_next_index_range"),
        sa.CheckConstraint("schema_version = 1", name="rgb_schema_version"),
        sa.CheckConstraint("length(sequence_id) BETWEEN 1 AND 64", name="rgb_sequence_id_length"),
        sa.CheckConstraint("length(payload_sha256) = 64", name="rgb_sha256_length"),
        sa.CheckConstraint(
            "payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="rgb_sha256_format",
        ),
        sa.CheckConstraint("answers ~ '^[A-E]+$'", name="rgb_answers_alphabet"),
        sa.CheckConstraint("length(answers) = item_count", name="rgb_answers_count"),
    )
    op.create_index(
        "ix_rgb_sequences_session_status",
        "rgb_sequences",
        ["session_id", "status"],
    )

    op.create_table(
        "session_result_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id"),
            nullable=False,
        ),
        sa.Column(
            "gateway_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("android_gateways.id"),
            nullable=False,
        ),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("cursor", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "active_sequence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rgb_sequences.id"),
            nullable=True,
        ),
        sa.Column("reason_code", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_session_result_deliveries"),
        sa.UniqueConstraint("session_id", name="uq_session_result_deliveries_session_id"),
        sa.CheckConstraint("cursor >= 0", name="result_delivery_cursor_nonnegative"),
        sa.CheckConstraint(
            "command IN ("
            "'RESULT_NOT_STARTED', 'RESULT_PROCESSING', "
            "'RGB_SEQUENCE_READY', 'RESULT_CANCELLED'"
            ")",
            name="result_delivery_command",
        ),
    )

    op.create_table(
        "rgb_sequence_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "rgb_sequence_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rgb_sequences.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("devices.id"),
            nullable=False,
        ),
        sa.Column(
            "gateway_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("android_gateways.id"),
            nullable=False,
        ),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("next_index", sa.Integer(), nullable=False),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=True),
        sa.Column("event_identity", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rgb_sequence_events"),
        sa.UniqueConstraint("event_identity", name="uq_rgb_sequence_events_event_identity"),
        sa.CheckConstraint("next_index >= 0", name="rgb_event_next_index_nonnegative"),
        sa.CheckConstraint("next_index <= item_count", name="rgb_event_next_index_max"),
        sa.CheckConstraint(
            "event IN ('RECEIVED', 'STARTED', 'RESUMED', 'COMPLETED', 'INVALID')",
            name="rgb_event_name",
        ),
        sa.CheckConstraint("item_count BETWEEN 1 AND 1000", name="rgb_event_item_count"),
    )
    op.create_index(
        "ix_rgb_sequence_events_sequence_received",
        "rgb_sequence_events",
        ["rgb_sequence_id", "received_at"],
    )
    op.create_index(
        "ix_rgb_sequence_events_gateway_idempotency",
        "rgb_sequence_events",
        ["gateway_id", "idempotency_key"],
    )

    op.create_index(
        "uq_rgb_sequences_active_session",
        "rgb_sequences",
        ["session_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('READY', 'RECEIVED', 'PLAYING')"),
    )


def downgrade() -> None:
    op.drop_index("uq_rgb_sequences_active_session", table_name="rgb_sequences")
    op.drop_index(
        "ix_rgb_sequence_events_gateway_idempotency",
        table_name="rgb_sequence_events",
    )
    op.drop_index(
        "ix_rgb_sequence_events_sequence_received",
        table_name="rgb_sequence_events",
    )
    op.drop_table("rgb_sequence_events")
    op.drop_table("session_result_deliveries")
    op.drop_index("ix_rgb_sequences_session_status", table_name="rgb_sequences")
    op.drop_table("rgb_sequences")
    op.drop_column("android_gateways", "metadata")
    op.drop_column("android_gateways", "device_model")
    op.drop_column("android_gateways", "app_version")
    op.drop_column("devices", "last_seen_at")
    op.drop_column("devices", "metadata")
    op.drop_column("devices", "firmware_version")
    op.drop_column("devices", "display_name")
