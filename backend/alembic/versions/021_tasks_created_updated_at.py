"""Add tasks.created_at and tasks.updated_at

Revision ID: 021
Revises: 020
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa

revision = "021"
down_revision = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )
    op.add_column(
        "tasks",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("tasks", "updated_at", schema="organizer")
    op.drop_column("tasks", "created_at", schema="organizer")
