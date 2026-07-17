"""Add accounts.credit_limit

Revision ID: 023
Revises: 022
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("credit_limit", sa.Numeric(12, 2), nullable=True),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("accounts", "credit_limit", schema="finance")
