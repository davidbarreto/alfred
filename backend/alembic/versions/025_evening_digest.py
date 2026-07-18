"""Add tasks.completed_at and briefings.type (morning/evening)

tasks.completed_at lets the evening digest detect one-off (non-recurring)
completions precisely -- status=DONE alone doesn't say when, and updated_at
also moves on unrelated edits. briefings.type turns the existing briefings
table into a generic daily-update store shared by the morning briefing and
the new evening digest, keyed by (date, type) instead of date alone.

Revision ID: 025
Revises: 024
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa

revision = "025"
down_revision = "024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="organizer",
    )

    op.add_column(
        "briefings",
        sa.Column("type", sa.String(length=20), nullable=False, server_default="morning"),
        schema="core",
    )
    op.alter_column("briefings", "type", server_default=None, schema="core")
    op.drop_constraint("uq_briefings_date", "briefings", schema="core", type_="unique")
    op.create_unique_constraint(
        "uq_briefings_date_type", "briefings", ["date", "type"], schema="core"
    )


def downgrade() -> None:
    op.drop_constraint("uq_briefings_date_type", "briefings", schema="core", type_="unique")
    op.create_unique_constraint("uq_briefings_date", "briefings", ["date"], schema="core")
    op.drop_column("briefings", "type", schema="core")

    op.drop_column("tasks", "completed_at", schema="organizer")
