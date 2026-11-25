"""Cities get coordinates and a cover photo, countries a cover, trips a photo album link

Phase 6 of the location domain. Schema only: the coordinates, the countries' missing ISO codes and the covers are
filled by the app (on city create) and by the one-off `scripts/backfill_city_covers.py`.

Upgrade: `location.cities` gains `latitude`/`longitude` (Numeric(9,6), both or neither) and the three cover columns
(`cover_path`, relative to MEDIA_STORAGE_DIR; `cover_credit`; `cover_source_url`); `location.countries` gains the cover
columns; `travel.trips` gains `photo_album_url` (http or https only).

Downgrade: drops them. The cover files stay in the media folder (nothing points at them any more).

Revision ID: 103
Revises: 102
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "103"
down_revision = "102"
branch_labels = None
depends_on = None

_COVER_COLUMNS = ("cover_path", "cover_credit", "cover_source_url")


def _add_cover_columns(table: str) -> None:
    op.add_column(table, sa.Column("cover_path", sa.String(200), nullable=True), schema="location")
    op.add_column(table, sa.Column("cover_credit", sa.Text(), nullable=True), schema="location")
    op.add_column(table, sa.Column("cover_source_url", sa.Text(), nullable=True), schema="location")


def upgrade() -> None:
    op.add_column("cities", sa.Column("latitude", sa.Numeric(9, 6), nullable=True), schema="location")
    op.add_column("cities", sa.Column("longitude", sa.Numeric(9, 6), nullable=True), schema="location")
    op.create_check_constraint(
        "ck_location_cities_coordinates", "cities", "(latitude IS NULL) = (longitude IS NULL)", schema="location"
    )
    _add_cover_columns("cities")
    _add_cover_columns("countries")
    op.add_column("trips", sa.Column("photo_album_url", sa.Text(), nullable=True), schema="travel")
    op.create_check_constraint(
        "ck_travel_trips_photo_album_url", "trips", "photo_album_url ~* '^https?://'", schema="travel"
    )


def downgrade() -> None:
    op.drop_constraint("ck_travel_trips_photo_album_url", "trips", schema="travel", type_="check")
    op.drop_column("trips", "photo_album_url", schema="travel")
    for table in ("countries", "cities"):
        for column in reversed(_COVER_COLUMNS):
            op.drop_column(table, column, schema="location")
    op.drop_constraint("ck_location_cities_coordinates", "cities", schema="location", type_="check")
    op.drop_column("cities", "longitude", schema="location")
    op.drop_column("cities", "latitude", schema="location")
