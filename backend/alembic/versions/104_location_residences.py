"""Places lived: location.residences

Phase 4 of the places adjustments. Schema only: the user types their rows in the portal (`/places/countries`).

Upgrade: creates `location.residences` (city RESTRICT, `from_date` null only on the birth row, `to_date` null while still
living there, `born`, `notes`, timestamps), a CHECK that a period ends after it starts, at most one birth row and at most
one open row (partial unique indexes). Overlaps are refused by the service.

Downgrade: drops the table (the rows go with it).

Revision ID: 104
Revises: 103
Create Date: 2026-11-26
"""
import sqlalchemy as sa
from alembic import op

revision = "104"
down_revision = "103"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "residences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("city_id", sa.Integer(), sa.ForeignKey("location.cities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("from_date", sa.Date(), nullable=True),
        sa.Column("to_date", sa.Date(), nullable=True),
        sa.Column("born", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("from_date IS NOT NULL OR born", name="ck_location_residences_from_date"),
        sa.CheckConstraint(
            "to_date IS NULL OR from_date IS NULL OR to_date > from_date", name="ck_location_residences_period"
        ),
        schema="location",
    )
    op.create_index("ix_location_residences_id", "residences", ["id"], schema="location")
    op.create_index("ix_location_residences_city_id", "residences", ["city_id"], schema="location")
    op.execute("CREATE UNIQUE INDEX uq_location_residences_born ON location.residences (born) WHERE born")
    op.execute(
        "CREATE UNIQUE INDEX uq_location_residences_open ON location.residences ((to_date IS NULL)) WHERE to_date IS NULL"
    )


def downgrade() -> None:
    op.drop_table("residences", schema="location")
