"""Add finance.currencies lookup table

Currency codes and display symbols were previously hardcoded in the web
portal (account creation dropdown + a Python symbol dict). This table makes
them user-manageable so a new currency doesn't require a code change.

Revision ID: 026
Revises: 025
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None

_SEED = [
    ("EUR", "€", "Euro"),
    ("USD", "$", "US Dollar"),
    ("BRL", "R$", "Brazilian Real"),
    ("GBP", "£", "British Pound"),
    ("PLN", "zł", "Polish Zloty"),
    ("CZK", "Kč", "Czech Koruna"),
]


def upgrade() -> None:
    op.create_table(
        "currencies",
        sa.Column("code", sa.String(10), primary_key=True),
        sa.Column("symbol", sa.String(10), nullable=True),
        sa.Column("name", sa.String(100), nullable=True),
        schema="finance",
    )
    for code, symbol, name in _SEED:
        op.execute(
            sa.text(
                "INSERT INTO finance.currencies (code, symbol, name) "
                "VALUES (:code, :symbol, :name)"
            ).bindparams(code=code, symbol=symbol, name=name)
        )


def downgrade() -> None:
    op.drop_table("currencies", schema="finance")
