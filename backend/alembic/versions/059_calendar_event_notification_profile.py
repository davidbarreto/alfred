"""Add notification_profile column to organizer.calendar_events

Calendar events only ever got a flat "starting in 2h" reminder. This column
lets each event opt into a named cascade profile (cant_miss/important/normal/
light/aware) so events with different importance get progressively earlier
Telegram alerts, matched by app.features.organizer.calendar_events.notifications.

Revision ID: 059
Revises: 058
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "059"
down_revision = "058"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column("notification_profile", sa.String(32), nullable=True),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("calendar_events", "notification_profile", schema="organizer")
