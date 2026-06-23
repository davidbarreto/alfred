"""Add finish_reason to integration.llm_calls

Revision ID: 007
Revises: 006
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa

revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_calls",
        sa.Column("finish_reason", sa.String(50), nullable=True),
        schema="integration",
    )


def downgrade() -> None:
    op.drop_column("llm_calls", "finish_reason", schema="integration")
