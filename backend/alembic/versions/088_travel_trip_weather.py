"""Save the weather shown for a trip

One row per trip, city and day holding the last forecast (or last year's climate far ahead) fetched
from Open-Meteo, refreshed on the first request of each day and kept after the trip ends. A finished trip
with days never saved gets them once from the archive (source `actual`).

Revision ID: 088
Revises: 087
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "088"
down_revision = "087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trip_weather",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("travel.trips.id", ondelete="CASCADE"), nullable=False),
        sa.Column("city_key", sa.String(200), nullable=False),
        sa.Column("city", sa.String(200), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("min_c", sa.Float(), nullable=True),
        sa.Column("max_c", sa.Float(), nullable=True),
        sa.Column("precip_mm", sa.Float(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("fetched_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("trip_id", "city_key", "day", name="uq_travel_trip_weather_day"),
        sa.CheckConstraint("source IN ('forecast', 'climate', 'actual')", name="ck_travel_trip_weather_source"),
        schema="travel",
    )
    op.create_index("ix_travel_trip_weather_id", "trip_weather", ["id"], schema="travel")


def downgrade() -> None:
    op.drop_index("ix_travel_trip_weather_id", table_name="trip_weather", schema="travel")
    op.drop_table("trip_weather", schema="travel")
