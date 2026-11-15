"""Links on cities and countries

A link is now owned by exactly one trip, place, city or country. The CHECK that allowed two owners is replaced, and
a URL is unique per city and per country like it is per trip and place.

Revision ID: 092
Revises: 091
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "092"
down_revision = "091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for owner, table in (("city", "cities"), ("country", "countries")):
        op.add_column("links", sa.Column(
            f"{owner}_id", sa.Integer(), sa.ForeignKey(f"travel.{table}.id", ondelete="CASCADE"), nullable=True
        ), schema="travel")
        op.create_index(f"ix_travel_links_{owner}_id", "links", [f"{owner}_id"], schema="travel")
        op.create_unique_constraint(f"uq_travel_links_{owner}_url", "links", [f"{owner}_id", "url"], schema="travel")
    op.drop_constraint("ck_travel_links_one_parent", "links", schema="travel", type_="check")
    op.create_check_constraint(
        "ck_travel_links_one_parent", "links",
        "num_nonnulls(trip_id, place_id, city_id, country_id) = 1", schema="travel",
    )


def downgrade() -> None:
    op.execute("DELETE FROM travel.links WHERE city_id IS NOT NULL OR country_id IS NOT NULL")
    op.drop_constraint("ck_travel_links_one_parent", "links", schema="travel", type_="check")
    op.create_check_constraint(
        "ck_travel_links_one_parent", "links",
        "(trip_id IS NOT NULL AND place_id IS NULL) OR (trip_id IS NULL AND place_id IS NOT NULL)", schema="travel",
    )
    for owner in ("country", "city"):
        op.drop_constraint(f"uq_travel_links_{owner}_url", "links", schema="travel", type_="unique")
        op.drop_index(f"ix_travel_links_{owner}_id", table_name="links", schema="travel")
        op.drop_column("links", f"{owner}_id", schema="travel")
