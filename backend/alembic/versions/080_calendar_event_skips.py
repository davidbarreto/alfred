"""Add organizer.calendar_event_skips

An occurrence of a recurring event the user will not attend. Alfred-only: the series in Google is
untouched, and the occurrence expansion leaves the skipped dates out.

Revision ID: 080
Revises: 079
Create Date: 2026-10-26
"""
from alembic import op
import sqlalchemy as sa

revision = "080"
down_revision = "079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_event_skips",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("organizer.calendar_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("event_id", "occurrence_date", name="uq_calendar_event_skips_event_date"),
        schema="organizer",
    )
    op.create_index("ix_calendar_event_skips_id", "calendar_event_skips", ["id"], schema="organizer")


def downgrade() -> None:
    op.drop_index("ix_calendar_event_skips_id", table_name="calendar_event_skips", schema="organizer")
    op.drop_table("calendar_event_skips", schema="organizer")
