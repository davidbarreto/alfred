"""Locations: the user's frequent everyday places

`organizer.locations` (home, office, school, shops) with address, Maps link, opening hours per weekday and
holidays (JSONB), and the shopping categories each one sells (`locations_shopping_categories`). Names are unique
case-insensitively; at most one location has kind `home`. No data step: the home address and the planning
travel times move here in later migrations.

Revision ID: 094
Revises: 093
Create Date: 2026-11-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "094"
down_revision = "093"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("maps_url", sa.Text(), nullable=True),
        sa.Column("opening_hours", postgresql.JSONB(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )
    op.create_index("ix_locations_id", "locations", ["id"], schema="organizer")
    op.create_index("uq_locations_name", "locations", [sa.text("lower(name)")], unique=True, schema="organizer")
    op.create_index(
        "uq_locations_home", "locations", ["kind"], unique=True, schema="organizer",
        postgresql_where=sa.text("kind = 'home'"),
    )
    op.create_table(
        "locations_shopping_categories",
        sa.Column(
            "location_id", sa.Integer(), sa.ForeignKey("organizer.locations.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("organizer.shopping_categories.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="organizer",
    )
    op.create_index(
        "ix_locations_shopping_categories_category_id", "locations_shopping_categories", ["category_id"],
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_locations_shopping_categories_category_id", table_name="locations_shopping_categories", schema="organizer"
    )
    op.drop_table("locations_shopping_categories", schema="organizer")
    op.drop_index("uq_locations_home", table_name="locations", schema="organizer")
    op.drop_index("uq_locations_name", table_name="locations", schema="organizer")
    op.drop_index("ix_locations_id", table_name="locations", schema="organizer")
    op.drop_table("locations", schema="organizer")
