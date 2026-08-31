"""Add vector embedding and FTS columns to knowledge_chunks — §24, §74.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-16

Adds:
- knowledge_chunks.embedding VECTOR(1536) for pgvector cosine search
- knowledge_chunks.fts TSVECTOR generated from text in Portuguese
- HNSW index on embedding for approximate nearest neighbour
- GIN index on fts for full-text search
- A trigger to keep fts synchronised with the text column

Note: dim=1536 matches text-embedding-3-small. Changing to a different
model with a different dimension requires a new migration + reindexation
(documented in docs/runbooks/).
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Stage 7: pgvector column — §24.3 / §74
    op.execute("""
        ALTER TABLE knowledge_chunks
        ADD COLUMN embedding vector(1536)
    """)

    # HNSW index — approximate nearest neighbour, cosine distance — §74
    op.execute("""
        CREATE INDEX ix_knowledge_chunks_embedding_hnsw
        ON knowledge_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    """)

    # Stage 8: FTS column — Portuguese + unaccent — §25
    op.execute("""
        ALTER TABLE knowledge_chunks
        ADD COLUMN fts tsvector
            GENERATED ALWAYS AS (
                to_tsvector('portuguese_unaccent', coalesce(text, ''))
            ) STORED
    """)

    # GIN index on fts column — §25
    op.execute("""
        CREATE INDEX ix_knowledge_chunks_fts_gin
        ON knowledge_chunks
        USING gin (fts)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_fts_gin")
    op.execute("DROP INDEX IF EXISTS ix_knowledge_chunks_embedding_hnsw")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS fts")
    op.execute("ALTER TABLE knowledge_chunks DROP COLUMN IF EXISTS embedding")
