"""configurable shopping categories

Revision ID: 033
Revises: 032
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None

_CATEGORIES = ["grocery", "pharmacy", "electronics", "online", "home", "clothes", "books", "other"]
_DEFAULT_CATEGORY = "other"

_ITEM_TABLES = ["shopping_items", "wishlist_items", "recurrence_items"]


def upgrade() -> None:
    op.create_table(
        "shopping_categories",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(50), nullable=False, unique=True),
        schema="organizer",
    )

    for name in _CATEGORIES:
        op.execute(
            sa.text(
                "INSERT INTO organizer.shopping_categories (name) "
                "SELECT :name WHERE NOT EXISTS "
                "(SELECT 1 FROM organizer.shopping_categories WHERE name = :name)"
            ).bindparams(name=name)
        )

    for table in _ITEM_TABLES:
        op.add_column(table, sa.Column("category_id", sa.Integer, nullable=True), schema="organizer")

        op.execute(sa.text(
            f"UPDATE organizer.{table} SET category_id = "
            f"(SELECT id FROM organizer.shopping_categories WHERE name = organizer.{table}.category)"
        ))
        op.execute(
            sa.text(
                f"UPDATE organizer.{table} SET category_id = "
                "(SELECT id FROM organizer.shopping_categories WHERE name = :default_name) "
                "WHERE category_id IS NULL"
            ).bindparams(default_name=_DEFAULT_CATEGORY)
        )

        op.alter_column(table, "category_id", nullable=False, schema="organizer")
        op.create_foreign_key(
            f"fk_{table}_category_id",
            table,
            "shopping_categories",
            ["category_id"],
            ["id"],
            source_schema="organizer",
            referent_schema="organizer",
            ondelete="RESTRICT",
        )
        op.create_index(f"idx_{table}_category_id", table, ["category_id"], schema="organizer")

    op.drop_index("idx_shopping_items_category", table_name="shopping_items", schema="organizer")
    op.drop_column("shopping_items", "category", schema="organizer")

    op.drop_index("idx_wishlist_items_category", table_name="wishlist_items", schema="organizer")
    op.drop_column("wishlist_items", "category", schema="organizer")

    op.drop_column("recurrence_items", "category", schema="organizer")


def downgrade() -> None:
    for table in _ITEM_TABLES:
        op.add_column(table, sa.Column("category", sa.String(50), nullable=True), schema="organizer")

        op.execute(sa.text(
            f"UPDATE organizer.{table} SET category = "
            f"(SELECT name FROM organizer.shopping_categories WHERE id = organizer.{table}.category_id)"
        ))

        op.alter_column(table, "category", nullable=False, server_default=_DEFAULT_CATEGORY, schema="organizer")
        op.drop_index(f"idx_{table}_category_id", table_name=table, schema="organizer")
        op.drop_constraint(f"fk_{table}_category_id", table, schema="organizer", type_="foreignkey")
        op.drop_column(table, "category_id", schema="organizer")

    op.create_index("idx_shopping_items_category", "shopping_items", ["category"], schema="organizer")
    op.create_index("idx_wishlist_items_category", "wishlist_items", ["category"], schema="organizer")

    op.drop_table("shopping_categories", schema="organizer")
