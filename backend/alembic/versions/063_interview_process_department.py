"""Add department column to organizer.interview_processes

Department/team was previously folded into the free-text notes field.
Splitting it out makes it filterable and lets the JD extraction and
portal forms target it directly.

Revision ID: 063
Revises: 062
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_processes",
        sa.Column("department", sa.String(255), nullable=True),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("interview_processes", "department", schema="organizer")
