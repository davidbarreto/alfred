"""Add production SRS state to language.chunks and production fields to language.sessions

Revision ID: 017
Revises: 016
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "017"
down_revision = "016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Production FSRS state, tracked independently from the recognition state.
    # prod_due_at is NULL until the chunk is unlocked for production practice
    # (first successful recognition review).
    op.add_column(
        "chunks",
        sa.Column("prod_stability", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        schema="language",
    )
    op.add_column(
        "chunks",
        sa.Column("prod_difficulty", sa.Float(), nullable=False, server_default=sa.text("5.0")),
        schema="language",
    )
    op.add_column(
        "chunks",
        sa.Column("prod_due_at", sa.DateTime(timezone=True), nullable=True),
        schema="language",
    )
    op.add_column(
        "chunks",
        sa.Column("prod_last_review_at", sa.DateTime(timezone=True), nullable=True),
        schema="language",
    )
    op.add_column(
        "chunks",
        sa.Column("prod_repetitions", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema="language",
    )
    op.add_column(
        "chunks",
        sa.Column("prod_lapses", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema="language",
    )
    op.add_column(
        "chunks",
        sa.Column("prod_consecutive_failures", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema="language",
    )
    op.add_column(
        "chunks",
        sa.Column("prod_state", sa.String(length=20), nullable=False, server_default=sa.text("'new'")),
        schema="language",
    )
    op.create_index("ix_language_chunks_prod_due_at", "chunks", ["prod_due_at"], schema="language")

    # Chunks that already passed at least one recognition review are unlocked immediately.
    op.execute("UPDATE language.chunks SET prod_due_at = now() WHERE repetitions >= 1")

    # Production attempt logging: which task type was used and what was asked.
    op.add_column(
        "sessions",
        sa.Column("task_type", sa.String(length=30), nullable=True),
        schema="language",
    )
    op.add_column(
        "sessions",
        sa.Column("prompt_text", sa.Text(), nullable=True),
        schema="language",
    )


def downgrade() -> None:
    op.drop_column("sessions", "prompt_text", schema="language")
    op.drop_column("sessions", "task_type", schema="language")

    op.drop_index("ix_language_chunks_prod_due_at", table_name="chunks", schema="language")
    op.drop_column("chunks", "prod_state", schema="language")
    op.drop_column("chunks", "prod_consecutive_failures", schema="language")
    op.drop_column("chunks", "prod_lapses", schema="language")
    op.drop_column("chunks", "prod_repetitions", schema="language")
    op.drop_column("chunks", "prod_last_review_at", schema="language")
    op.drop_column("chunks", "prod_due_at", schema="language")
    op.drop_column("chunks", "prod_difficulty", schema="language")
    op.drop_column("chunks", "prod_stability", schema="language")
