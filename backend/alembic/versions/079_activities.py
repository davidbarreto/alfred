"""Add organizer.activities, activities_tags and activity_logs

Activities are optional gap fillers (read a book, go to the gym), not tasks: no deadline, no done
state. Logging an activity is what counts as done; archiving keeps the logs.

Revision ID: 079
Revises: 078
Create Date: 2026-10-25
"""
from alembic import op
import sqlalchemy as sa

revision = "079"
down_revision = "078"
branch_labels = None
depends_on = None

_CONTEXTS = ("computer", "phone", "home", "out", "anywhere")


def upgrade() -> None:
    op.create_table(
        "activities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("min_minutes", sa.Integer(), nullable=True),
        sa.Column("max_minutes", sa.Integer(), nullable=True),
        sa.Column("context", sa.String(16), nullable=True),
        sa.Column("target_per_week", sa.Integer(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("min_minutes > 0", name="ck_activities_min_minutes"),
        sa.CheckConstraint("max_minutes > 0", name="ck_activities_max_minutes"),
        sa.CheckConstraint("max_minutes IS NULL OR min_minutes IS NULL OR max_minutes >= min_minutes", name="ck_activities_min_max"),
        sa.CheckConstraint("target_per_week > 0", name="ck_activities_target_per_week"),
        sa.CheckConstraint("context IN ({})".format(", ".join(f"'{c}'" for c in _CONTEXTS)), name="ck_activities_context"),
        schema="organizer",
    )
    op.create_index("ix_activities_id", "activities", ["id"], schema="organizer")

    op.create_table(
        "activities_tags",
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("organizer.activities.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("organizer.tags.id", ondelete="CASCADE"), primary_key=True),
        schema="organizer",
    )

    op.create_table(
        "activity_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("activity_id", sa.Integer(), sa.ForeignKey("organizer.activities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("minutes > 0", name="ck_activity_logs_minutes"),
        schema="organizer",
    )
    op.create_index("ix_activity_logs_id", "activity_logs", ["id"], schema="organizer")
    op.create_index("ix_activity_logs_activity_done_at", "activity_logs", ["activity_id", "done_at"], schema="organizer")


def downgrade() -> None:
    op.drop_index("ix_activity_logs_activity_done_at", table_name="activity_logs", schema="organizer")
    op.drop_index("ix_activity_logs_id", table_name="activity_logs", schema="organizer")
    op.drop_table("activity_logs", schema="organizer")
    op.drop_table("activities_tags", schema="organizer")
    op.drop_index("ix_activities_id", table_name="activities", schema="organizer")
    op.drop_table("activities", schema="organizer")
