"""Coordinates on locations

`organizer.locations.latitude` and `longitude` (both or neither, CHECK `ck_locations_coordinates`), so the weather can
be looked up for a location (the default weather place is Home). Filled from the location form or from the
coordinates in its Maps link.

Revision ID: 099
Revises: 098
Create Date: 2026-11-25
"""
import sqlalchemy as sa
from alembic import op

revision = "099"
down_revision = "098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("locations", sa.Column("latitude", sa.Numeric(9, 6), nullable=True), schema="organizer")
    op.add_column("locations", sa.Column("longitude", sa.Numeric(9, 6), nullable=True), schema="organizer")
    op.create_check_constraint(
        "ck_locations_coordinates", "locations", "(latitude IS NULL) = (longitude IS NULL)", schema="organizer"
    )


def downgrade() -> None:
    op.drop_constraint("ck_locations_coordinates", "locations", schema="organizer", type_="check")
    op.drop_column("locations", "longitude", schema="organizer")
    op.drop_column("locations", "latitude", schema="organizer")
