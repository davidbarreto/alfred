"""Add contacts.relationship

Revision ID: 034
Revises: 033
Create Date: 2026-07-23
"""
from alembic import op
import sqlalchemy as sa

revision = "034"
down_revision = "033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("relationship", sa.String(20), nullable=True),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("contacts", "relationship", schema="organizer")
