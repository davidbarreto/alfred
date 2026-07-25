"""Add command_executions.source

Revision ID: 037
Revises: 036
Create Date: 2026-07-25
"""
from alembic import op
import sqlalchemy as sa

revision = "037"
down_revision = "036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "command_executions",
        sa.Column("source", sa.String(30), nullable=True),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("command_executions", "source", schema="core")
