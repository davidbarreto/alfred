"""Add planning fields to organizer.tasks

estimate_minutes, context and available_from are Alfred-only (never sent to Notion).
They let an LLM client place a task in a day plan.

Revision ID: 076
Revises: 075
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None

_CONTEXTS = ("computer", "phone", "home", "out", "anywhere")


def upgrade() -> None:
    op.add_column("tasks", sa.Column("estimate_minutes", sa.Integer(), nullable=True), schema="organizer")
    op.add_column("tasks", sa.Column("context", sa.String(16), nullable=True), schema="organizer")
    op.add_column("tasks", sa.Column("available_from", sa.DateTime(timezone=True), nullable=True), schema="organizer")
    op.create_check_constraint(
        "ck_tasks_estimate_minutes_positive", "tasks", "estimate_minutes > 0", schema="organizer"
    )
    op.create_check_constraint(
        "ck_tasks_context",
        "tasks",
        "context IN ({})".format(", ".join(f"'{c}'" for c in _CONTEXTS)),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tasks_context", "tasks", schema="organizer", type_="check")
    op.drop_constraint("ck_tasks_estimate_minutes_positive", "tasks", schema="organizer", type_="check")
    op.drop_column("tasks", "available_from", schema="organizer")
    op.drop_column("tasks", "context", schema="organizer")
    op.drop_column("tasks", "estimate_minutes", schema="organizer")
