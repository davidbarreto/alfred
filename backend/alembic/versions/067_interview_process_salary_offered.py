"""Add salary_offered column to organizer.interview_processes

salary_min/salary_max represent the range discussed during the process;
salary_offered captures the actual figure extended in an offer, which can
differ from that range and was previously buried in free-text notes.

Revision ID: 067
Revises: 066
Create Date: 2026-09-19
"""
from alembic import op
import sqlalchemy as sa

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "interview_processes",
        sa.Column("salary_offered", sa.Integer(), nullable=True),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("interview_processes", "salary_offered", schema="organizer")
