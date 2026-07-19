"""Add timezone column to organizer.calendar_events

Meetings synced from Google Calendar (e.g. a recurring US Central Time
call) were stored as a naive local wall-clock time with no origin
timezone, so they silently drifted by an hour whenever the US and EU
DST transitions fell on different weeks. Storing the event's own IANA
timezone lets the portal convert to the viewer's selected display
timezone correctly across DST boundaries.

Revision ID: 027
Revises: 026
Create Date: 2026-07-19
"""
from alembic import op
import sqlalchemy as sa

revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column("timezone", sa.String(64), nullable=True),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("calendar_events", "timezone", schema="organizer")
