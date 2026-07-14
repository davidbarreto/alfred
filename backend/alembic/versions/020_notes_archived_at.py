"""Add notes.archived_at

Revision ID: 020
Revises: 019
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "020"
down_revision = "019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notes", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True), schema="organizer")


def downgrade() -> None:
    op.drop_column("notes", "archived_at", schema="organizer")
