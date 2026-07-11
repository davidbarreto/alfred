"""Add unique constraint on working_memory.key

Revision ID: 019
Revises: 018
Create Date: 2026-07-11
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_core_working_memory_key", "working_memory", ["key"], schema="core"
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_core_working_memory_key", "working_memory", schema="core", type_="unique"
    )
