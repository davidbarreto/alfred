"""Make shopping_items/wishlist_items.category_id nullable so soft-deleted rows can
release their category, letting shopping_categories become deletable once no active
item references them (they still block delete via RESTRICT while category_id is set)

Revision ID: 040
Revises: 039
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa

revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "shopping_items", "category_id", existing_type=sa.Integer(), nullable=True, schema="organizer"
    )
    op.alter_column(
        "wishlist_items", "category_id", existing_type=sa.Integer(), nullable=True, schema="organizer"
    )


def downgrade() -> None:
    op.alter_column(
        "wishlist_items", "category_id", existing_type=sa.Integer(), nullable=False, schema="organizer"
    )
    op.alter_column(
        "shopping_items", "category_id", existing_type=sa.Integer(), nullable=False, schema="organizer"
    )
