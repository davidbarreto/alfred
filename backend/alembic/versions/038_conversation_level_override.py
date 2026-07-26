"""Add conversation_threads.level_override

Revision ID: 038
Revises: 037
Create Date: 2026-07-26
"""
from alembic import op
import sqlalchemy as sa

revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_threads",
        sa.Column("level_override", sa.String(5), nullable=True),
        schema="language",
    )


def downgrade() -> None:
    op.drop_column("conversation_threads", "level_override", schema="language")
