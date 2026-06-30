"""seed default finance account

Revision ID: 013
Revises: 012
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO finance.accounts (name, type, currency, balance, is_active, created_at, updated_at)
            SELECT 'Main Account', 'checking', 'EUR', 0, true, now(), now()
            WHERE NOT EXISTS (SELECT 1 FROM finance.accounts)
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM finance.accounts WHERE name = 'Main Account'"
        )
    )
