"""seed common finance categories

Revision ID: 014
Revises: 013
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "014"
down_revision = "013"
branch_labels = None
depends_on = None

_CATEGORIES = [
    "Groceries",
    "Restaurants & Cafes",
    "Transport",
    "Health",
    "Entertainment",
    "Shopping",
    "Utilities",
    "Subscriptions",
    "Travel",
    "Sports & Fitness",
    "Education",
    "Personal Care",
    "Home",
    "Other",
]


def upgrade() -> None:
    for name in _CATEGORIES:
        op.execute(
            sa.text(
                "INSERT INTO finance.categories (name) "
                "SELECT :name WHERE NOT EXISTS "
                "(SELECT 1 FROM finance.categories WHERE name = :name)"
            ).bindparams(name=name)
        )


def downgrade() -> None:
    names = ", ".join(f"'{n}'" for n in _CATEGORIES)
    op.execute(sa.text(f"DELETE FROM finance.categories WHERE name IN ({names})"))
