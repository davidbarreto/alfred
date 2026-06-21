"""add shopping list tables

Revision ID: 003
Revises: 002
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "shopping_items",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="other"),
        sa.Column("priority", sa.String(10), nullable=False, server_default="need"),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("estimated_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("store", sa.String(255), nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("last_bought_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )
    op.create_index("idx_shopping_items_status", "shopping_items", ["status"], schema="organizer")
    op.create_index("idx_shopping_items_category", "shopping_items", ["category"], schema="organizer")

    op.create_table(
        "wishlist_items",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="other"),
        sa.Column("estimated_price", sa.Numeric(10, 2), nullable=True),
        sa.Column("brand", sa.String(255), nullable=True),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )
    op.create_index("idx_wishlist_items_category", "wishlist_items", ["category"], schema="organizer")

    op.create_table(
        "recurrence_items",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False, server_default="other"),
        sa.Column("recurrence_days", sa.Integer, nullable=False),
        sa.Column("last_added_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )
    op.create_index("idx_recurrence_items_active", "recurrence_items", ["active"], schema="organizer")


def downgrade() -> None:
    op.drop_index("idx_recurrence_items_active", table_name="recurrence_items", schema="organizer")
    op.drop_table("recurrence_items", schema="organizer")

    op.drop_index("idx_wishlist_items_category", table_name="wishlist_items", schema="organizer")
    op.drop_table("wishlist_items", schema="organizer")

    op.drop_index("idx_shopping_items_category", table_name="shopping_items", schema="organizer")
    op.drop_index("idx_shopping_items_status", table_name="shopping_items", schema="organizer")
    op.drop_table("shopping_items", schema="organizer")
