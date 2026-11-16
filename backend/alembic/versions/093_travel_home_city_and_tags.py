"""Home city snapshot on trips and default tags on cities and countries

A trip can carry its own home (city, address) and its own airport times, so changing the travel settings later does
not rewrite how a past trip was planned. `default_tag_names` on cities and countries are finance tag names that are
only summed (never stamped on transactions).

Revision ID: 093
Revises: 092
Create Date: 2026-11-16
"""
from alembic import op
import sqlalchemy as sa

revision = "093"
down_revision = "092"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cities", sa.Column("default_tag_names", sa.Text(), nullable=True), schema="travel")
    op.add_column("countries", sa.Column("default_tag_names", sa.Text(), nullable=True), schema="travel")
    op.add_column("trips", sa.Column(
        "home_city_id", sa.Integer(), sa.ForeignKey("travel.cities.id", ondelete="RESTRICT"), nullable=True
    ), schema="travel")
    op.create_index("ix_travel_trips_home_city_id", "trips", ["home_city_id"], schema="travel")
    op.add_column("trips", sa.Column("home_address", sa.Text(), nullable=True), schema="travel")
    op.add_column("trips", sa.Column("airport_buffer_min", sa.Integer(), nullable=True), schema="travel")
    op.add_column("trips", sa.Column("home_to_airport_min", sa.Integer(), nullable=True), schema="travel")


def downgrade() -> None:
    op.drop_column("trips", "home_to_airport_min", schema="travel")
    op.drop_column("trips", "airport_buffer_min", schema="travel")
    op.drop_column("trips", "home_address", schema="travel")
    op.drop_index("ix_travel_trips_home_city_id", table_name="trips", schema="travel")
    op.drop_column("trips", "home_city_id", schema="travel")
    op.drop_column("countries", "default_tag_names", schema="travel")
    op.drop_column("cities", "default_tag_names", schema="travel")
