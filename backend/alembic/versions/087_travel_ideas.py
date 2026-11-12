"""Link travel visits to a calendar event

A timed visit gets a Google Calendar event; the id is kept on the visit so editing the visit
updates the same event. Unique like legs and stays (086): an event belongs to one item. A deleted
event simply unlinks (SET NULL).

Revision ID: 087
Revises: 086
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "087"
down_revision = "086"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "visits",
        sa.Column(
            "calendar_event_id", sa.Integer(), sa.ForeignKey("organizer.calendar_events.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="travel",
    )
    op.create_unique_constraint("uq_travel_visits_calendar_event_id", "visits", ["calendar_event_id"], schema="travel")


def downgrade() -> None:
    op.drop_constraint("uq_travel_visits_calendar_event_id", "visits", schema="travel", type_="unique")
    op.drop_column("visits", "calendar_event_id", schema="travel")
