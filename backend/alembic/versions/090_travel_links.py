"""Links (tips, official sites, videos) attached to a trip or a place

One row per saved URL, owned by exactly one trip or place. Visits and stays do not carry links of their own:
a visit shows its place's links.

Revision ID: 090
Revises: 089
Create Date: 2026-11-15
"""
from alembic import op
import sqlalchemy as sa

revision = "090"
down_revision = "089"
branch_labels = None
depends_on = None

_KINDS = ("website", "instagram", "tiktok", "video", "article", "map", "booking", "other")


def upgrade() -> None:
    op.create_table(
        "links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trip_id", sa.Integer(), sa.ForeignKey("travel.trips.id", ondelete="CASCADE"), nullable=True),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("travel.places.id", ondelete="CASCADE"), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(300), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(trip_id IS NOT NULL AND place_id IS NULL) OR (trip_id IS NULL AND place_id IS NOT NULL)",
            name="ck_travel_links_one_parent",
        ),
        sa.CheckConstraint("kind IN ({})".format(", ".join(f"'{k}'" for k in _KINDS)), name="ck_travel_links_kind"),
        sa.UniqueConstraint("trip_id", "url", name="uq_travel_links_trip_url"),
        sa.UniqueConstraint("place_id", "url", name="uq_travel_links_place_url"),
        schema="travel",
    )
    op.create_index("ix_travel_links_id", "links", ["id"], schema="travel")
    op.create_index("ix_travel_links_trip_id", "links", ["trip_id"], schema="travel")
    op.create_index("ix_travel_links_place_id", "links", ["place_id"], schema="travel")


def downgrade() -> None:
    op.drop_index("ix_travel_links_place_id", table_name="links", schema="travel")
    op.drop_index("ix_travel_links_trip_id", table_name="links", schema="travel")
    op.drop_index("ix_travel_links_id", table_name="links", schema="travel")
    op.drop_table("links", schema="travel")
