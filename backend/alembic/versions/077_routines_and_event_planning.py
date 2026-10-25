"""Add organizer.routines, organizer.routine_steps and planning columns on calendar_events

Routines are daily-life rhythm (no done state, never notify). Event planning columns
(availability, presence, travel_minutes, routine_id) are Alfred-only: never sent to Google.

Revision ID: 077
Revises: 076
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = "077"
down_revision = "076"
branch_labels = None
depends_on = None

_CONTEXTS = ("computer", "phone", "home", "out", "anywhere")
_AVAILABILITIES = ("blocked", "light", "free")
_PRESENCES = ("in_person", "remote_home", "remote_anywhere")


def _in(column: str, values: tuple[str, ...]) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))


def upgrade() -> None:
    op.create_table(
        "routines",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("recurrence_rule", sa.String(500), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("(recurrence_rule IS NULL) = (starts_on IS NULL)", name="ck_routines_rule_starts_on"),
        schema="organizer",
    )
    op.create_index("ix_routines_id", "routines", ["id"], schema="organizer")

    op.create_table(
        "routine_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "routine_id", sa.Integer(), sa.ForeignKey("organizer.routines.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("anchor", sa.String(5), nullable=True),
        sa.Column("offset_minutes", sa.Integer(), nullable=True),
        sa.Column("window_start", sa.Time(), nullable=True),
        sa.Column("window_end", sa.Time(), nullable=True),
        sa.Column("context", sa.String(16), nullable=True),
        sa.Column("location", sa.String(255), nullable=True),
        sa.Column(
            "checklist_note_id", sa.Integer(), sa.ForeignKey("organizer.notes.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("routine_id", "position", name="uq_routine_steps_routine_position"),
        sa.CheckConstraint("duration_minutes >= 0", name="ck_routine_steps_duration"),
        sa.CheckConstraint(_in("anchor", ("start", "end")), name="ck_routine_steps_anchor"),
        sa.CheckConstraint(_in("context", _CONTEXTS), name="ck_routine_steps_context"),
        sa.CheckConstraint("window_end IS NULL OR window_end > window_start", name="ck_routine_steps_window_order"),
        sa.CheckConstraint(
            "(anchor IS NOT NULL AND offset_minutes IS NOT NULL AND window_start IS NULL AND window_end IS NULL)"
            " OR (anchor IS NULL AND offset_minutes IS NULL AND window_start IS NOT NULL AND window_end IS NOT NULL)",
            name="ck_routine_steps_timing_form",
        ),
        schema="organizer",
    )
    op.create_index("ix_routine_steps_id", "routine_steps", ["id"], schema="organizer")

    op.add_column("calendar_events", sa.Column("availability", sa.String(16), nullable=True), schema="organizer")
    op.add_column(
        "calendar_events",
        sa.Column("presence", sa.String(16), nullable=False, server_default="in_person"),
        schema="organizer",
    )
    op.add_column(
        "calendar_events",
        sa.Column("travel_minutes", sa.Integer(), nullable=False, server_default="0"),
        schema="organizer",
    )
    op.add_column(
        "calendar_events",
        sa.Column("routine_id", sa.Integer(), sa.ForeignKey("organizer.routines.id", ondelete="SET NULL"), nullable=True),
        schema="organizer",
    )
    op.create_check_constraint(
        "ck_calendar_events_availability",
        "calendar_events",
        "availability IS NULL OR " + _in("availability", _AVAILABILITIES),
        schema="organizer",
    )
    op.create_check_constraint(
        "ck_calendar_events_presence", "calendar_events", _in("presence", _PRESENCES), schema="organizer"
    )
    op.create_check_constraint(
        "ck_calendar_events_travel_minutes", "calendar_events", "travel_minutes >= 0", schema="organizer"
    )


def downgrade() -> None:
    op.drop_constraint("ck_calendar_events_travel_minutes", "calendar_events", schema="organizer", type_="check")
    op.drop_constraint("ck_calendar_events_presence", "calendar_events", schema="organizer", type_="check")
    op.drop_constraint("ck_calendar_events_availability", "calendar_events", schema="organizer", type_="check")
    op.drop_column("calendar_events", "routine_id", schema="organizer")
    op.drop_column("calendar_events", "travel_minutes", schema="organizer")
    op.drop_column("calendar_events", "presence", schema="organizer")
    op.drop_column("calendar_events", "availability", schema="organizer")
    op.drop_index("ix_routine_steps_id", table_name="routine_steps", schema="organizer")
    op.drop_table("routine_steps", schema="organizer")
    op.drop_index("ix_routines_id", table_name="routines", schema="organizer")
    op.drop_table("routines", schema="organizer")
