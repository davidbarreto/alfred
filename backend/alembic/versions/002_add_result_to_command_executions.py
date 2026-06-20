"""add result to command_executions

Revision ID: 002
Revises: 001
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "command_executions",
        sa.Column("result", JSONB, nullable=True),
        schema="core",
    )


def downgrade() -> None:
    op.drop_column("command_executions", "result", schema="core")
