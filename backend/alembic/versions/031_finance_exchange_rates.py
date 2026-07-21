"""Add finance.exchange_rates cache table and transactions.amount_eur

Revision ID: 031
Revises: 030
Create Date: 2026-07-21
"""
from alembic import op
import sqlalchemy as sa

revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("rate_date", sa.Date, nullable=False),
        sa.Column("currency", sa.String(10), nullable=False),
        sa.Column("rate", sa.Numeric(18, 6), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        schema="finance",
    )
    op.create_unique_constraint(
        "uq_exchange_rates_date_currency",
        "exchange_rates",
        ["rate_date", "currency"],
        schema="finance",
    )
    op.add_column(
        "transactions",
        sa.Column("amount_eur", sa.Numeric(12, 2), nullable=True),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("transactions", "amount_eur", schema="finance")
    op.drop_constraint(
        "uq_exchange_rates_date_currency", "exchange_rates", schema="finance", type_="unique"
    )
    op.drop_table("exchange_rates", schema="finance")
