"""Add llm_calls.is_audio and roleplay conversation tables

Revision ID: 035
Revises: 034
Create Date: 2026-07-24
"""

from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("is_audio", sa.Boolean(), nullable=False, server_default="false"),
        schema="integration",
    )

    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("chat_session_id", sa.Integer(), nullable=False),
        sa.Column("scenario", sa.Text(), nullable=False),
        sa.Column("voice_reply", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tip", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["track_id"], ["language.tracks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chat_session_id"], ["core.sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="language",
    )
    op.create_index("ix_language_conversation_threads_id", "conversation_threads", ["id"], schema="language")
    op.create_index(
        "ix_language_conversation_threads_track_id", "conversation_threads", ["track_id"], schema="language"
    )

    op.create_table(
        "conversation_turns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("thread_id", sa.Integer(), nullable=False),
        sa.Column("message_id", sa.Integer(), nullable=False),
        sa.Column("is_audio", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("audio_ref", sa.String(500), nullable=True),
        sa.Column("tip", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["thread_id"], ["language.conversation_threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["core.messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        schema="language",
    )
    op.create_index("ix_language_conversation_turns_id", "conversation_turns", ["id"], schema="language")
    op.create_index(
        "ix_language_conversation_turns_thread_id", "conversation_turns", ["thread_id"], schema="language"
    )


def downgrade() -> None:
    op.drop_table("conversation_turns", schema="language")
    op.drop_table("conversation_threads", schema="language")
    op.drop_column("llm_calls", "is_audio", schema="integration")
