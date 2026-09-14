"""Add core.pause_log table

Records each completed global-pause ("Take a breath") cycle: when it
started/ended and how many tasks had their urgency reset or deadline
shifted on resume, so pause history can be surfaced in Insights.

Revision ID: 065
Revises: 064
Create Date: 2026-09-14
"""
from alembic import op
import sqlalchemy as sa

revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pause_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tasks_urgency_reset", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_deadline_shifted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema="core",
    )


def downgrade() -> None:
    op.drop_table("pause_log", schema="core")
