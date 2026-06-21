"""add notes timestamps and shopping source

Revision ID: 004
Revises: 003
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notes",
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="organizer",
    )
    op.add_column(
        "notes",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        schema="organizer",
    )
    op.add_column(
        "shopping_items",
        sa.Column("source", sa.String(50), nullable=True),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("notes", "created_at", schema="organizer")
    op.drop_column("notes", "updated_at", schema="organizer")
    op.drop_column("shopping_items", "source", schema="organizer")
