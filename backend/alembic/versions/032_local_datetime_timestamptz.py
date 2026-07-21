"""Convert calendar_events start/end and tasks.deadline to timestamptz (LocalDateTime)

Revision ID: 032
Revises: 031
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None

# Settings.timezone value in effect for all existing naive rows. Not the
# per-row calendar_events.timezone column -- that records each event's own
# *origin* zone (e.g. a Google Calendar event's own timeZone), while every
# write path already normalizes naive values to this app-wide zone
# regardless of origin.
_APP_ZONE = "Europe/Lisbon"


def upgrade() -> None:
    for col in ("start_datetime", "end_datetime"):
        op.alter_column(
            "calendar_events", col,
            type_=sa.DateTime(timezone=True),
            existing_type=sa.DateTime(),
            postgresql_using=f"{col} AT TIME ZONE '{_APP_ZONE}'",
            schema="organizer",
        )
    op.alter_column(
        "tasks", "deadline",
        type_=sa.DateTime(timezone=True),
        existing_type=sa.DateTime(),
        existing_nullable=True,
        postgresql_using=f"deadline AT TIME ZONE '{_APP_ZONE}'",
        schema="organizer",
    )


def downgrade() -> None:
    op.alter_column(
        "tasks", "deadline",
        type_=sa.DateTime(),
        existing_type=sa.DateTime(timezone=True),
        existing_nullable=True,
        postgresql_using=f"deadline AT TIME ZONE '{_APP_ZONE}'",
        schema="organizer",
    )
    for col in ("start_datetime", "end_datetime"):
        op.alter_column(
            "calendar_events", col,
            type_=sa.DateTime(),
            existing_type=sa.DateTime(timezone=True),
            postgresql_using=f"{col} AT TIME ZONE '{_APP_ZONE}'",
            schema="organizer",
        )
