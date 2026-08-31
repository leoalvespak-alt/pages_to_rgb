"""Initial schema — all tables, extensions, and base indexes.

Revision ID: 0001
Revises:
Create Date: 2026-08-16
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extensions (must come before any table that uses them) ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    # Create a text search configuration that applies unaccent
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_ts_config WHERE cfgname = 'portuguese_unaccent'
            ) THEN
                CREATE TEXT SEARCH CONFIGURATION portuguese_unaccent
                    (COPY = portuguese);
                ALTER TEXT SEARCH CONFIGURATION portuguese_unaccent
                    ALTER MAPPING FOR hword, hword_part, word
                    WITH unaccent, portuguese_stem;
            END IF;
        END
        $$;
    """)

    # --- devices ---
    op.create_table(
        "devices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("device_code", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_devices_device_code", "devices", ["device_code"])

    # --- android_gateways ---
    op.create_table(
        "android_gateways",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("gateway_code", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_android_gateways_gateway_code", "android_gateways", ["gateway_code"]
    )

    # --- sessions ---
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("public_id", sa.Text, nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("gateway_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("android_gateways.id"), nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("expected_pages", sa.Integer, nullable=False),
        sa.Column("expected_questions", sa.Integer, nullable=False),
        sa.Column("minimum_ratio", sa.Numeric(4, 3), nullable=False),
        sa.Column("capture_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capture_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_reason", sa.Text, nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("provider_snapshot", postgresql.JSONB, nullable=True),
        sa.Column("degraded_mode", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_sessions_public_id", "sessions", ["public_id"])

    # --- captures ---
    op.create_table(
        "captures",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("capture_id", sa.Text, nullable=False),
        sa.Column("mode", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'open'")),
        sa.Column("requested_frames", sa.Integer, nullable=True),
        sa.Column("received_frames", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("command_cursor", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_captures_session_id_capture_id", "captures", ["session_id", "capture_id"]
    )

    # --- frames ---
    op.create_table(
        "frames",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("capture_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("captures.id"), nullable=True),
        sa.Column("frame_index", sa.Integer, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("mime_type", sa.Text, nullable=False),
        sa.Column("quality_metrics", postgresql.JSONB, nullable=True),
        sa.Column("late_upload", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_frames_capture_id_frame_index", "frames", ["capture_id", "frame_index"]
    )
    op.create_unique_constraint(
        "uq_frames_session_sha256_capture_index",
        "frames", ["session_id", "sha256", "capture_id", "frame_index"]
    )

    # --- logical_pages ---
    op.create_table(
        "logical_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("logical_index", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False, server_default=sa.text("'ok'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_logical_pages_session_id_logical_index",
        "logical_pages", ["session_id", "logical_index"]
    )

    # --- logical_page_frames ---
    op.create_table(
        "logical_page_frames",
        sa.Column("logical_page_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("logical_pages.id"), nullable=False),
        sa.Column("frame_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("frames.id"), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("rank", sa.Integer, nullable=False),
    )
    op.create_primary_key(
        "pk_logical_page_frames",
        "logical_page_frames",
        ["logical_page_id", "frame_id"],
    )

    # --- image_artifacts ---
    op.create_table(
        "image_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("logical_page_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("logical_pages.id"), nullable=True),
        sa.Column("artifact_type", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_image_artifacts_session_type",
        "image_artifacts", ["session_id", "artifact_type"]
    )

    # --- ocr_runs ---
    op.create_table(
        "ocr_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("logical_page_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("logical_pages.id"), nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("confidence", sa.Float, nullable=True),
        sa.Column("raw_storage_key", sa.Text, nullable=True),
        sa.Column("metadata_", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_ocr_runs_logical_page_provider_attempt",
        "ocr_runs", ["logical_page_id", "provider", "attempt"]
    )

    # --- questions ---
    op.create_table(
        "questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("question_number", sa.Integer, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("text", sa.Text, nullable=True),
        sa.Column("alternatives", postgresql.JSONB, nullable=True),
        sa.Column("page_refs", postgresql.JSONB, nullable=True),
        sa.Column("media_refs", postgresql.JSONB, nullable=True),
        sa.Column("ocr_refs", postgresql.JSONB, nullable=True),
        sa.Column("reconstruction_metadata", postgresql.JSONB, nullable=True),
        sa.Column("failure_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint(
        "uq_questions_session_id_question_number",
        "questions", ["session_id", "question_number"]
    )

    # --- knowledge_documents ---
    op.create_table(
        "knowledge_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("discipline", sa.Text, nullable=True),
        sa.Column("subject", sa.Text, nullable=True),
        sa.Column("source_type", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_knowledge_documents_discipline_subject_active",
        "knowledge_documents", ["discipline", "subject", "active"]
    )

    # --- knowledge_chunks (base columns — vector/fts added in 0002) ---
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("knowledge_documents.id"), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("page_number", sa.Integer, nullable=True),
        sa.Column("section", sa.Text, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
    )
    op.create_index(
        "ix_knowledge_chunks_document_id",
        "knowledge_chunks", ["document_id"]
    )

    # --- retrieval_runs ---
    op.create_table(
        "retrieval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("query", sa.Text, nullable=False),
        sa.Column("provider", sa.Text, nullable=False),
        sa.Column("results", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_retrieval_runs_question_id",
        "retrieval_runs", ["question_id"]
    )

    # --- answer_attempts ---
    op.create_table(
        "answer_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("role", sa.Text, nullable=False),
        sa.Column("attempt", sa.Integer, nullable=False),
        sa.Column("provider", sa.Text, nullable=True),
        sa.Column("model", sa.Text, nullable=True),
        sa.Column("answer", sa.Text, nullable=True),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("prompt_version", sa.Text, nullable=True),
        sa.Column("prompt_hash", sa.String(64), nullable=True),
        sa.Column("latency_ms", sa.Float, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("degraded_provider", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("evidence_refs", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_answer_attempts_question_role_attempt",
        "answer_attempts", ["question_id", "role", "attempt"]
    )

    # --- final_answers ---
    op.create_table(
        "final_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("question_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("questions.id"), nullable=False),
        sa.Column("answer", sa.Text, nullable=False),
        sa.Column("decision_source", sa.Text, nullable=False),
        sa.Column("validated", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("degraded_provider", sa.Boolean, nullable=False,
                  server_default=sa.text("false")),
        sa.Column("evidence_refs", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_final_answers_question_id", "final_answers", ["question_id"])

    # --- audio_artifacts ---
    op.create_table(
        "audio_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("artifact_type", sa.Text, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "ix_audio_artifacts_session_type",
        "audio_artifacts", ["session_id", "artifact_type"]
    )

    # --- audit_events ---
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("sessions.id"), nullable=True),
        sa.Column("event_type", sa.Text, nullable=False),
        sa.Column("stage", sa.Text, nullable=True),
        sa.Column("severity", sa.Text, nullable=False, server_default=sa.text("'info'")),
        sa.Column("reason_code", sa.Text, nullable=True),
        sa.Column("actor_type", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_audit_events_session_created", "audit_events", ["session_id", "created_at"])
    op.create_index("ix_audit_events_event_type", "audit_events", ["event_type"])

    # --- idempotency_keys ---
    op.create_table(
        "idempotency_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("scope", sa.Text, nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("response_status", sa.Integer, nullable=True),
        sa.Column("response_body", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_unique_constraint("uq_idempotency_keys_key_scope", "idempotency_keys", ["key", "scope"])
    op.create_index("ix_idempotency_keys_expires_at", "idempotency_keys", ["expires_at"])

    # --- storage_orphans ---
    op.create_table(
        "storage_orphans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("bucket", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_table("storage_orphans")
    op.drop_table("idempotency_keys")
    op.drop_table("audit_events")
    op.drop_table("audio_artifacts")
    op.drop_table("final_answers")
    op.drop_table("answer_attempts")
    op.drop_table("retrieval_runs")
    op.drop_table("knowledge_chunks")
    op.drop_table("knowledge_documents")
    op.drop_table("questions")
    op.drop_table("ocr_runs")
    op.drop_table("image_artifacts")
    op.drop_table("logical_page_frames")
    op.drop_table("logical_pages")
    op.drop_table("frames")
    op.drop_table("captures")
    op.drop_table("sessions")
    op.drop_table("android_gateways")
    op.drop_table("devices")

    op.execute("DROP TEXT SEARCH CONFIGURATION IF EXISTS portuguese_unaccent")
    op.execute("DROP EXTENSION IF EXISTS unaccent")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
    op.execute("DROP EXTENSION IF EXISTS vector")
