"""Add opening_balance/opening_balance_date to finance.accounts

Optional manual anchor point for net worth history: some bank exports
(ActivoBank, Revolut) carry a running balance per statement line, which lets
you seed a known-true balance as of a specific date. Net worth before that
date (or for accounts with no anchor) is assumed to start at 0 and is
reconstructed purely from the transaction ledger -- Account.balance itself is
a manually-edited snapshot with no guaranteed link to transaction history, so
it can't be used for this.

Revision ID: 053
Revises: 052
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

revision = "053"
down_revision = "052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("opening_balance", sa.Numeric(12, 2), nullable=True),
        schema="finance",
    )
    op.add_column(
        "accounts",
        sa.Column("opening_balance_date", sa.Date(), nullable=True),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("accounts", "opening_balance_date", schema="finance")
    op.drop_column("accounts", "opening_balance", schema="finance")
