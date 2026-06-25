"""Create language schema with tracks, grammar_scope, chunks, sessions tables

Revision ID: 009
Revises: 008
Create Date: 2026-06-25
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS language")

    op.create_table(
        "tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("level", sa.String(5), nullable=False, server_default="A1"),
        sa.Column("daily_quota", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("review_mode", sa.String(20), nullable=False, server_default="balanced"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_language_tracks_code"),
        schema="language",
    )
    op.create_index("ix_language_tracks_id", "tracks", ["id"], schema="language")

    op.create_table(
        "grammar_scope",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(20), nullable=False, server_default="deferred"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["track_id"], ["language.tracks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("track_id", "category", "value", name="uq_grammar_scope_track_category_value"),
        schema="language",
    )
    op.create_index("ix_language_grammar_scope_id", "grammar_scope", ["id"], schema="language")

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("grammar_scope_id", sa.Integer(), nullable=True),
        sa.Column("chunk_type", sa.String(20), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("translation", sa.String(500), nullable=False),
        sa.Column("example_sentence", sa.String(1000), nullable=True),
        sa.Column("example_translation", sa.String(1000), nullable=True),
        sa.Column("cefr_level", sa.String(5), nullable=True),
        sa.Column("frequency_rank", sa.Integer(), nullable=True),
        sa.Column("frequency_source", sa.String(30), nullable=True),
        sa.Column("stability", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("difficulty", sa.Float(), nullable=False, server_default="5.0"),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("repetitions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lapses", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("state", sa.String(20), nullable=False, server_default="new"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending_triage"),
        sa.Column("is_leech", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["track_id"], ["language.tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["grammar_scope_id"], ["language.grammar_scope.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="language",
    )
    op.create_index("ix_language_chunks_id", "chunks", ["id"], schema="language")
    op.create_index("ix_language_chunks_track_id", "chunks", ["track_id"], schema="language")
    op.create_index("ix_language_chunks_due_at", "chunks", ["due_at"], schema="language")
    op.create_index("ix_language_chunks_frequency_rank", "chunks", ["frequency_rank"], schema="language")

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.Integer(), nullable=True),
        sa.Column("session_type", sa.String(20), nullable=False),
        sa.Column("feeds_srs", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("audio_ref", sa.String(500), nullable=True),
        sa.Column("gemini_feedback_json", JSONB(), nullable=True),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("transcript_or_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["track_id"], ["language.tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chunk_id"], ["language.chunks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="language",
    )
    op.create_index("ix_language_sessions_id", "sessions", ["id"], schema="language")
    op.create_index("ix_language_sessions_track_id", "sessions", ["track_id"], schema="language")
    op.create_index("ix_language_sessions_chunk_id", "sessions", ["chunk_id"], schema="language")
    op.create_index("ix_language_sessions_created_at", "sessions", ["created_at"], schema="language")


def downgrade() -> None:
    op.drop_table("sessions", schema="language")
    op.drop_table("chunks", schema="language")
    op.drop_table("grammar_scope", schema="language")
    op.drop_table("tracks", schema="language")
    op.execute("DROP SCHEMA IF EXISTS language")
