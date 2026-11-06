"""Let budget_targets point at a tag instead of a category, and seed travel categories and tags

A tag budget is versioned per cycle exactly like a category budget. Transactions carrying a
budgeted tag count toward the tag's budget instead of their category's. Exactly one of
category_id / tag_id is set. Closed (historic) tag targets are removed with their tag; a tag
with an open target is refused at the service layer.

Also seeds two categories for trip spending and a starter set of tags (trips, car, house,
utilities, leisure, tech, context). Names are matched case-insensitively, so anything already
created by hand is left alone. The downgrade removes only seeded rows nothing references, so it
never detaches real data.

Revision ID: 083
Revises: 082
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None

_CATEGORIES = ["Intercity Transport", "Accommodation"]
_TAGS = [
    # Trips
    "Travel", "Car Rental", "Hotel", "Hostel", "Airbnb", "Ride", "Tours",
    # Car
    "Car", "Fuel",
    # House
    "Home Rent", "Repairs", "Appliances", "Furniture", "Decoration", "Kitchenware",
    # Utilities
    "Water", "Energy", "Home Gas", "Telecom",
    # Leisure
    "Cinema", "Concerts", "Museums", "Music", "Gym", "Theater", "Festivals", "Nightlife",
    "Games", "Books", "Sports Events", "Streaming",
    # Tech and money
    "Tech", "Interest",
    # Context
    "Work", "Family", "Delivery",
]


def upgrade() -> None:
    op.alter_column("budget_targets", "category_id", existing_type=sa.Integer(), nullable=True, schema="finance")
    op.add_column(
        "budget_targets",
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("finance.tags.id", ondelete="CASCADE"), nullable=True),
        schema="finance",
    )
    op.create_check_constraint(
        "ck_budget_targets_one_subject",
        "budget_targets",
        "(category_id IS NULL) <> (tag_id IS NULL)",
        schema="finance",
    )
    op.create_index(
        "ux_budget_targets_tag_open",
        "budget_targets",
        ["tag_id"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("effective_to IS NULL AND tag_id IS NOT NULL"),
    )
    for table, names in (("categories", _CATEGORIES), ("tags", _TAGS)):
        for name in names:
            op.execute(
                sa.text(
                    f"INSERT INTO finance.{table} (name) "
                    f"SELECT :name WHERE NOT EXISTS "
                    f"(SELECT 1 FROM finance.{table} WHERE lower(name) = lower(:name))"
                ).bindparams(name=name)
            )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM finance.categories c WHERE c.name = ANY(:names) "
            "AND NOT EXISTS (SELECT 1 FROM finance.transactions t WHERE t.category_id = c.id) "
            "AND NOT EXISTS (SELECT 1 FROM finance.budget_targets b WHERE b.category_id = c.id)"
        ).bindparams(sa.bindparam("names", _CATEGORIES, type_=sa.ARRAY(sa.String)))
    )
    op.execute(
        sa.text(
            "DELETE FROM finance.tags g WHERE g.name = ANY(:names) "
            "AND NOT EXISTS (SELECT 1 FROM finance.transactions_tags tt WHERE tt.tag_id = g.id) "
            "AND NOT EXISTS (SELECT 1 FROM finance.budget_targets b WHERE b.tag_id = g.id)"
        ).bindparams(sa.bindparam("names", _TAGS, type_=sa.ARRAY(sa.String)))
    )
    op.drop_index("ux_budget_targets_tag_open", table_name="budget_targets", schema="finance")
    op.execute("DELETE FROM finance.budget_targets WHERE tag_id IS NOT NULL")
    op.drop_constraint("ck_budget_targets_one_subject", "budget_targets", schema="finance", type_="check")
    op.drop_column("budget_targets", "tag_id", schema="finance")
    op.alter_column("budget_targets", "category_id", existing_type=sa.Integer(), nullable=False, schema="finance")
