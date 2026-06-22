"""make command_executions.message_id nullable for web portal traceability

Revision ID: 005
Revises: 004
Create Date: 2026-06-22
"""
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "command_executions",
        "message_id",
        nullable=True,
        schema="core",
    )


def downgrade() -> None:
    # Rows with message_id IS NULL must be removed before re-adding NOT NULL
    op.execute("DELETE FROM core.command_executions WHERE message_id IS NULL")
    op.alter_column(
        "command_executions",
        "message_id",
        nullable=False,
        schema="core",
    )
