"""Add first_reviewed_at column to language.chunks

Marks the moment a chunk left state="new" for the first time, independent
of its rating (including Again, which does not bump repetitions/lapses on
a brand-new card). Used to count how many new chunks a track has already
introduced today, so recognition batches can throttle new-card intake via
tracks.new_cards_per_day without also delaying scheduled reviews.

Revision ID: 050
Revises: 049
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = "050"
down_revision = "049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chunks",
        sa.Column("first_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        schema="language",
    )
    op.create_index(
        "ix_language_chunks_first_reviewed_at",
        "chunks",
        ["first_reviewed_at"],
        schema="language",
    )


def downgrade() -> None:
    op.drop_index("ix_language_chunks_first_reviewed_at", table_name="chunks", schema="language")
    op.drop_column("chunks", "first_reviewed_at", schema="language")
