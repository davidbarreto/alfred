"""Add core.settings generic key-value config table

Backs configurable, cross-module app settings -- first consumer is
finance.cycle_start_day (customizable "month" cycle for reports/budgets).
Absent keys are treated as unset by callers (each module's typed facade
supplies its own default), so no seed rows are needed here.

Revision ID: 052
Revises: 051
Create Date: 2026-08-15
"""
from alembic import op
import sqlalchemy as sa

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("settings", schema="core")
