"""Add organizer.shopping_products; shopping_items point at a product

Every purchase used to be a new shopping_items row carrying its own name and category, so one thing
bought five times was five unrelated rows. A product is now the single row per thing; shopping_items
are its list entries / purchases. At most one live pending entry per product.

Products are created from the distinct lower(name) of the existing rows (spelling, category and unit
taken from the most recent live row). Duplicate pending rows of one product keep the newest; the
others are soft-deleted. shopping_items.name and category_id are dropped; the downgrade restores
them from the product.

Revision ID: 081
Revises: 080
Create Date: 2026-11-01
"""
from alembic import op
import sqlalchemy as sa

revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("organizer.shopping_categories.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("default_unit", sa.String(50), nullable=True),
        sa.Column("default_quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        schema="organizer",
    )
    op.create_index("ix_shopping_products_id", "shopping_products", ["id"], schema="organizer")
    op.execute(
        "CREATE UNIQUE INDEX uq_shopping_products_name ON organizer.shopping_products (lower(name)) "
        "WHERE deleted_at IS NULL"
    )

    # One product per distinct lower(name). A name whose rows are all soft-deleted becomes a deleted product.
    op.execute(
        """
        INSERT INTO organizer.shopping_products (name, category_id, default_unit, deleted_at, created_at, updated_at)
        SELECT DISTINCT ON (lower(name))
            name,
            category_id,
            unit,
            CASE WHEN bool_or(deleted_at IS NULL) OVER (PARTITION BY lower(name)) THEN NULL
                 ELSE max(deleted_at) OVER (PARTITION BY lower(name)) END,
            min(created_at) OVER (PARTITION BY lower(name)),
            now()
        FROM organizer.shopping_items
        ORDER BY lower(name), (deleted_at IS NULL) DESC, created_at DESC, id DESC
        """
    )
    # Latest row was soft-deleted (category cleared) or had none: fall back to any row's category, then "other".
    op.execute(
        """
        UPDATE organizer.shopping_products p
        SET category_id = (
            SELECT i.category_id FROM organizer.shopping_items i
            WHERE lower(i.name) = lower(p.name) AND i.category_id IS NOT NULL
            ORDER BY i.created_at DESC, i.id DESC LIMIT 1
        )
        WHERE p.category_id IS NULL AND p.deleted_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE organizer.shopping_products
        SET category_id = (SELECT id FROM organizer.shopping_categories WHERE name = 'other')
        WHERE category_id IS NULL AND deleted_at IS NULL
        """
    )

    op.add_column("shopping_items", sa.Column("product_id", sa.Integer(), nullable=True), schema="organizer")
    op.execute(
        """
        UPDATE organizer.shopping_items i
        SET product_id = p.id
        FROM organizer.shopping_products p
        WHERE lower(i.name) = lower(p.name)
        """
    )
    op.alter_column("shopping_items", "product_id", existing_type=sa.Integer(), nullable=False, schema="organizer")
    op.create_foreign_key(
        "fk_shopping_items_product_id",
        "shopping_items",
        "shopping_products",
        ["product_id"],
        ["id"],
        source_schema="organizer",
        referent_schema="organizer",
        ondelete="RESTRICT",
    )
    op.create_index("ix_shopping_items_product_id", "shopping_items", ["product_id"], schema="organizer")

    # Keep the newest pending entry of each product, soft-delete the older duplicates.
    op.execute(
        """
        UPDATE organizer.shopping_items
        SET deleted_at = now(), updated_at = now()
        WHERE status = 'pending' AND deleted_at IS NULL
          AND id NOT IN (
              SELECT max(id) FROM organizer.shopping_items
              WHERE status = 'pending' AND deleted_at IS NULL
              GROUP BY product_id
          )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_shopping_items_pending_product ON organizer.shopping_items (product_id) "
        "WHERE status = 'pending' AND deleted_at IS NULL"
    )

    op.drop_column("shopping_items", "name", schema="organizer")
    op.drop_column("shopping_items", "category_id", schema="organizer")


def downgrade() -> None:
    op.add_column("shopping_items", sa.Column("name", sa.String(255), nullable=True), schema="organizer")
    op.add_column(
        "shopping_items",
        sa.Column(
            "category_id", sa.Integer(), sa.ForeignKey("organizer.shopping_categories.id", ondelete="RESTRICT"), nullable=True
        ),
        schema="organizer",
    )
    op.execute(
        """
        UPDATE organizer.shopping_items i
        SET name = p.name,
            category_id = CASE WHEN i.deleted_at IS NULL THEN p.category_id ELSE NULL END
        FROM organizer.shopping_products p
        WHERE i.product_id = p.id
        """
    )
    op.alter_column("shopping_items", "name", existing_type=sa.String(255), nullable=False, schema="organizer")

    op.execute("DROP INDEX organizer.uq_shopping_items_pending_product")
    op.drop_index("ix_shopping_items_product_id", table_name="shopping_items", schema="organizer")
    op.drop_constraint("fk_shopping_items_product_id", "shopping_items", schema="organizer", type_="foreignkey")
    op.drop_column("shopping_items", "product_id", schema="organizer")

    op.execute("DROP INDEX organizer.uq_shopping_products_name")
    op.drop_index("ix_shopping_products_id", table_name="shopping_products", schema="organizer")
    op.drop_table("shopping_products", schema="organizer")
