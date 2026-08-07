"""Add grading_status to language.sessions

Revision ID: 047
Revises: 046
Create Date: 2026-08-07
"""
from alembic import op
import sqlalchemy as sa

revision = "047"
down_revision = "046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column("grading_status", sa.String(20), nullable=False, server_default="done"),
        schema="language",
    )


def downgrade() -> None:
    op.drop_column("sessions", "grading_status", schema="language")
