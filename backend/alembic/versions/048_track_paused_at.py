"""Add paused_at column to language.tracks

Lets a track be temporarily paused so it drops out of briefings,
reminders, and daily review/shadow/produce batches without losing
its chunks or SRS progress. Resuming shifts each chunk's due dates
forward by the paused duration so the user isn't hit with a fake
overdue backlog.

Revision ID: 048
Revises: 047
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = "048"
down_revision = "047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        schema="language",
    )


def downgrade() -> None:
    op.drop_column("tracks", "paused_at", schema="language")
