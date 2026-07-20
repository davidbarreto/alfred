"""Replace budgets with per-category monthly budget_targets history

Revision ID: 030
Revises: 029
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("budgets", schema="finance")

    op.create_table(
        "budget_targets",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("finance.categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("effective_from", sa.DateTime, nullable=False),
        sa.Column("effective_to", sa.DateTime, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        schema="finance",
    )
    op.create_index(
        "ux_budget_targets_open",
        "budget_targets",
        ["category_id"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("effective_to IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("budget_targets", schema="finance")

    op.create_table(
        "budgets",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("finance.categories.id", ondelete="SET NULL"), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("period", sa.String(20), nullable=False),
        sa.Column("starts_at", sa.DateTime, nullable=True),
        sa.Column("ends_at", sa.DateTime, nullable=True),
        schema="finance",
    )
