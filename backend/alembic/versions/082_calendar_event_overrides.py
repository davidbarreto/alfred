"""Add organizer.calendar_event_overrides

One occurrence of a recurring event moved to another time. The series is untouched; the occurrence
expansion swaps the original span for the override. Written through to Google Calendar as an
exception of that instance.

Revision ID: 082
Revises: 081
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa

revision = "082"
down_revision = "081"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "calendar_event_overrides",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("organizer.calendar_events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_date", sa.Date(), nullable=False),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("event_id", "occurrence_date", name="uq_calendar_event_overrides_event_date"),
        sa.CheckConstraint("end_datetime >= start_datetime", name="ck_calendar_event_overrides_order"),
        schema="organizer",
    )
    op.create_index("ix_calendar_event_overrides_id", "calendar_event_overrides", ["id"], schema="organizer")


def downgrade() -> None:
    op.drop_index("ix_calendar_event_overrides_id", table_name="calendar_event_overrides", schema="organizer")
    op.drop_table("calendar_event_overrides", schema="organizer")
