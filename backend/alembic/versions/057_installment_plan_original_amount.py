"""Add finance.installment_plans.original_amount

Plan identity moved from a one-time "Fracionada" signal in ActivoBank PDF
movements to the installment schedule table itself, which carries the
original (unamortized) purchase price on every row of a plan ("Valor
Transação"). Storing it lets any future import -- CSV or PDF, in any order
-- match a plan's original lump-sum transaction by (account, description,
amount) alone, without depending on catching the specific statement the
purchase happened in.

Nullable: a manually-created plan (e.g. a Cetelem/Nubank financed purchase
whose monthly charge is its own real transaction, not a split of one
upfront purchase) has no lump sum to ever match/supersede, so it's never
given an original_amount -- the matching step simply skips plans where this
is null.

Revision ID: 057
Revises: 056
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "installment_plans",
        sa.Column("original_amount", sa.Numeric(12, 2), nullable=True),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("installment_plans", "original_amount", schema="finance")
