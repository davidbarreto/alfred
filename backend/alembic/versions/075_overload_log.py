"""Add core.overload_log table

One row per day the reminder run executed, recording how backed-up the task list
got (peak overdue/urgent counts, worst level reached) and how many tasks the
reminder digests listed or left out, for the portal banner and Insights.

Revision ID: 075
Revises: 074
Create Date: 2026-10-23
"""
from alembic import op
import sqlalchemy as sa

revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "overload_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False, unique=True),
        sa.Column("level", sa.String(16), nullable=False),
        sa.Column("last_level", sa.String(16), nullable=False),
        sa.Column("peak_overdue", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("peak_urgent", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("peak_active", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reminder_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_listed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tasks_omitted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_overloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("level IN ('ok', 'elevated', 'overloaded')", name="ck_overload_log_level"),
        sa.CheckConstraint("last_level IN ('ok', 'elevated', 'overloaded')", name="ck_overload_log_last_level"),
        schema="core",
    )
    op.create_index("ix_overload_log_id", "overload_log", ["id"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_overload_log_id", table_name="overload_log", schema="core")
    op.drop_table("overload_log", schema="core")
