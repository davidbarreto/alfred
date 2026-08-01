"""Add duration_ms to core.command_executions

Revision ID: 042
Revises: 041
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa

revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "command_executions",
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("command_executions", "duration_ms", schema="core")
