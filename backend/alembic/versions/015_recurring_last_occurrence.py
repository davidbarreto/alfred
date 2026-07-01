"""add last_occurrence_date to recurring_transactions

Revision ID: 015
Revises: 014
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa

revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "recurring_transactions",
        sa.Column("last_occurrence_date", sa.Date(), nullable=True),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("recurring_transactions", "last_occurrence_date", schema="finance")
