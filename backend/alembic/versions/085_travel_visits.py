"""Add travel visits and place tags

A visit is one occurrence of going to a place (a dinner, a museum day), planned, visited or
missed, optionally inside a trip. Deleting a trip detaches its visits (SET NULL) so notes and
grades survive; a place with visits can't be deleted (RESTRICT).

Revision ID: 085
Revises: 084
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "085"
down_revision = "084"
branch_labels = None
depends_on = None

_SCHEMA = "travel"


def upgrade() -> None:
    op.create_table(
        "visits",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="planned"),
        sa.Column("visit_date", sa.Date(), nullable=True),
        sa.Column("visit_time", sa.Time(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("grade", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["place_id"], ["travel.places.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trip_id"], ["travel.trips.id"], ondelete="SET NULL"),
        sa.CheckConstraint("status IN ('planned', 'visited', 'missed')", name="ck_travel_visits_status"),
        sa.CheckConstraint("grade IS NULL OR grade BETWEEN 1 AND 5", name="ck_travel_visits_grade"),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_visits_id", "visits", ["id"], schema=_SCHEMA)
    op.create_index("ix_travel_visits_place_id", "visits", ["place_id"], schema=_SCHEMA)
    op.create_index("ix_travel_visits_trip_date", "visits", ["trip_id", "visit_date"], schema=_SCHEMA)

    op.create_table(
        "places_tags",
        sa.Column("place_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["place_id"], ["travel.places.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["travel.tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("place_id", "tag_id"),
        schema=_SCHEMA,
    )
    op.create_index("ix_travel_places_tags_tag_id", "places_tags", ["tag_id"], schema=_SCHEMA)


def downgrade() -> None:
    op.drop_table("places_tags", schema=_SCHEMA)
    op.drop_table("visits", schema=_SCHEMA)
