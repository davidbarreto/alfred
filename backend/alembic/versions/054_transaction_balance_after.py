"""Add balance_after to finance.transactions

Some bank exports (ActivoBank checking, Banco Inter, Revolut) report the
account's running balance immediately after each transaction. That value is
already parsed at import time (ParsedRow.balance_after) but was discarded
between preview and commit. Persisting it lets net worth and Account.balance
be reconstructed from a real, self-correcting checkpoint instead of purely
from summed deltas.

Revision ID: 054
Revises: 053
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "054"
down_revision = "053"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("balance_after", sa.Numeric(12, 2), nullable=True),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("transactions", "balance_after", schema="finance")
