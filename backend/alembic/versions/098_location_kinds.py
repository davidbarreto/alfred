"""Location kinds are a fixed set

`organizer.locations.kind` was free text; it is now one of a fixed set (CHECK `ck_locations_kind`, the same list as
`LOCATION_KINDS`), so clients can find a place by kind (the office is kind work). An existing "office" becomes work;
any other kind outside the set becomes other.

Revision ID: 098
Revises: 097
Create Date: 2026-11-24
"""
from alembic import op

revision = "098"
down_revision = "097"
branch_labels = None
depends_on = None

_KINDS = (
    "home", "work", "school", "gym", "sports", "supermarket", "pharmacy", "bakery", "market", "mall", "variety_store",
    "hardware_store", "shop", "restaurant", "cafe", "health", "park", "playground", "venue", "other",
)
_IN_KINDS = ", ".join(f"'{kind}'" for kind in _KINDS)


def upgrade() -> None:
    op.execute("UPDATE organizer.locations SET kind = 'work' WHERE kind = 'office'")
    op.execute(f"UPDATE organizer.locations SET kind = 'other' WHERE kind NOT IN ({_IN_KINDS})")
    op.create_check_constraint("ck_locations_kind", "locations", f"kind IN ({_IN_KINDS})", schema="organizer")


def downgrade() -> None:
    op.drop_constraint("ck_locations_kind", "locations", schema="organizer", type_="check")
