"""Calendar events can sit at a location

`organizer.calendar_events.location_id` (FK `organizer.locations`, ON DELETE SET NULL, null): the frequent place an
event happens at, so the day plan derives travel between locations from their travel times. Alfred-only: never
sent to Google and never written by sync. On a recurring series it sits on the master row (every occurrence).

Revision ID: 097
Revises: 096
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa

revision = "097"
down_revision = "096"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "calendar_events",
        sa.Column(
            "location_id",
            sa.Integer(),
            sa.ForeignKey("organizer.locations.id", ondelete="SET NULL", name="fk_calendar_events_location_id"),
            nullable=True,
        ),
        schema="organizer",
    )
    op.create_index("ix_calendar_events_location_id", "calendar_events", ["location_id"], schema="organizer")


def downgrade() -> None:
    op.drop_index("ix_calendar_events_location_id", table_name="calendar_events", schema="organizer")
    op.drop_constraint("fk_calendar_events_location_id", "calendar_events", schema="organizer", type_="foreignkey")
    op.drop_column("calendar_events", "location_id", schema="organizer")
