"""Create travel schema (trips, legs, stays, places, tags)

Phase 1 of the travel module: trips with their legs (flights, trains, ...) and stays (lodging),
the places stays point at, and a tag vocabulary for trips. Deleting a trip cascades to its legs
and detaches (SET NULL) its stays; a place with stays can't be deleted (RESTRICT).

Revision ID: 084
Revises: 083
Create Date: 2026-11-10
"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import make_url

revision = "084"
down_revision = "083"
branch_labels = None
depends_on = None

_SCHEMA = "travel"
_PLACE_KINDS = "('hotel', 'restaurant', 'cafe', 'activity', 'museum', 'attraction', 'shop', 'other')"
_LEG_MODES = "('flight', 'train', 'bus', 'ferry', 'car', 'other')"


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_tags_id", "tags", ["id"], schema=_SCHEMA)
    op.execute("CREATE UNIQUE INDEX uq_travel_tags_name_lower ON travel.tags (lower(name))")

    op.create_table(
        "trips",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("travelers", sa.Text(), nullable=True),
        sa.Column("preferences", sa.Text(), nullable=True),
        sa.Column("checklist_note_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("default_tag_names", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["checklist_note_id"], ["organizer.notes.id"], ondelete="SET NULL"),
        sa.CheckConstraint("end_date >= start_date", name="ck_travel_trips_dates"),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_trips_id", "trips", ["id"], schema=_SCHEMA)
    op.create_index("ix_travel_trips_start_date", "trips", ["start_date"], schema=_SCHEMA)

    op.create_table(
        "trips_tags",
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["trip_id"], ["travel.trips.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["travel.tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trip_id", "tag_id"),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_trips_tags_tag_id", "trips_tags", ["tag_id"], schema=_SCHEMA)

    op.create_table(
        "places",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("maps_url", sa.Text(), nullable=True),
        sa.Column("lat", sa.Float(), nullable=True),
        sa.Column("lng", sa.Float(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(f"kind IN {_PLACE_KINDS}", name="ck_travel_places_kind"),
        sa.CheckConstraint(
            "(lat IS NULL OR lat BETWEEN -90 AND 90) AND (lng IS NULL OR lng BETWEEN -180 AND 180)",
            name="ck_travel_places_coordinates",
        ),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_places_id", "places", ["id"], schema=_SCHEMA)

    op.create_table(
        "legs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("origin", sa.String(200), nullable=False),
        sa.Column("destination", sa.String(200), nullable=False),
        sa.Column("origin_code", sa.String(8), nullable=True),
        sa.Column("destination_code", sa.String(8), nullable=True),
        sa.Column("departs_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrives_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("departs_tz", sa.String(64), nullable=False),
        sa.Column("arrives_tz", sa.String(64), nullable=False),
        sa.Column("carrier", sa.String(100), nullable=True),
        sa.Column("number", sa.String(32), nullable=True),
        sa.Column("booking_ref", sa.String(64), nullable=True),
        sa.Column("booking_url", sa.Text(), nullable=True),
        sa.Column("seat", sa.String(64), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["trip_id"], ["travel.trips.id"], ondelete="CASCADE"),
        sa.CheckConstraint(f"mode IN {_LEG_MODES}", name="ck_travel_legs_mode"),
        sa.CheckConstraint("arrives_at >= departs_at", name="ck_travel_legs_arrives_after_departs"),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_legs_id", "legs", ["id"], schema=_SCHEMA)
    op.create_index("ix_travel_legs_trip_departs", "legs", ["trip_id", "departs_at"], schema=_SCHEMA)

    op.create_table(
        "stays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=True),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("check_in_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("check_out_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("booking_ref", sa.String(64), nullable=True),
        sa.Column("booking_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("grade", sa.Integer(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["trip_id"], ["travel.trips.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["place_id"], ["travel.places.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("check_out_at >= check_in_at", name="ck_travel_stays_out_after_in"),
        sa.CheckConstraint("grade IS NULL OR grade BETWEEN 1 AND 5", name="ck_travel_stays_grade"),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_stays_id", "stays", ["id"], schema=_SCHEMA)
    op.create_index("ix_travel_stays_place_id", "stays", ["place_id"], schema=_SCHEMA)
    op.create_index("ix_travel_stays_trip_check_in", "stays", ["trip_id", "check_in_at"], schema=_SCHEMA)

    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if app_user:
        op.execute(f"GRANT USAGE ON SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}"
        )
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT USAGE, SELECT ON SEQUENCES TO {app_user}")


def downgrade() -> None:
    op.drop_table("stays", schema=_SCHEMA)
    op.drop_table("legs", schema=_SCHEMA)
    op.drop_table("places", schema=_SCHEMA)
    op.drop_table("trips_tags", schema=_SCHEMA)
    op.drop_table("trips", schema=_SCHEMA)
    op.drop_table("tags", schema=_SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA}")
