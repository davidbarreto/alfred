"""Create study schema (tracks, plans, plan items, tags) and drop cs study plans

Study plans stop being a CS concern: the planner will read interview signals and
story gaps too, so it gets its own schema and cs stays an evidence source.
Plans become targeted (one gap each, backlog + global cap) instead of weekly/monthly.

Existing cs.study_plans rows are not carried over (prod had a single stale plan the
user chose to delete), so the new tables start empty. downgrade() recreates the old
cs tables empty, with their original columns.
organizer.interview_processes.study_plan_id is dropped too (never used by the portal).

Revision ID: 070
Revises: 069
Create Date: 2026-09-27
"""
from alembic import op
import sqlalchemy as sa

revision = "070"
down_revision = "069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS study")

    op.create_table(
        "tracks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_study_tracks_name"),
        schema="study",
    )
    op.create_index("ix_study_tracks_id", "tracks", ["id"], schema="study")
    op.execute(
        "INSERT INTO study.tracks (name, description) VALUES ("
        "'Software Engineering', "
        "'Algorithms, APIs and system design, architecture concepts and behavioural interview skills')"
    )

    op.create_table(
        "plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("track_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["track_id"], ["study.tracks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('backlog', 'active', 'completed', 'abandoned')", name="ck_study_plans_status"),
        sa.CheckConstraint("priority IN ('low', 'medium', 'high')", name="ck_study_plans_priority"),
        schema="study",
    )
    op.create_index("ix_study_plans_id", "plans", ["id"], schema="study")
    op.create_index("ix_study_plans_track_id", "plans", ["track_id"], schema="study")
    op.create_index("ix_study_plans_status", "plans", ["status"], schema="study")

    op.create_table(
        "plan_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_type", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["study.plans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "source_type IN ('cs_tag', 'interview_stage', 'interview_process', 'story_gap', 'manual')",
            name="ck_study_plan_items_source_type",
        ),
        schema="study",
    )
    op.create_index("ix_study_plan_items_id", "plan_items", ["id"], schema="study")
    op.create_index("ix_study_plan_items_plan_id", "plan_items", ["plan_id"], schema="study")

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_study_tags_name"),
        schema="study",
    )
    op.create_index("ix_study_tags_id", "tags", ["id"], schema="study")

    op.create_table(
        "plans_tags",
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["study.plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["study.tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id", "tag_id"),
        schema="study",
    )

    op.drop_column("interview_processes", "study_plan_id", schema="organizer")
    op.drop_table("study_plan_items", schema="cs")
    op.drop_table("study_plans", schema="cs")


def downgrade() -> None:
    op.create_table(
        "study_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        schema="cs",
    )
    op.create_index("ix_cs_study_plans_id", "study_plans", ["id"], schema="cs")
    op.create_index("ix_cs_study_plans_cadence", "study_plans", ["cadence"], schema="cs")

    op.create_table(
        "study_plan_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("problem_id", sa.Integer(), nullable=True),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("is_done", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["cs.study_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["cs.problems.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="cs",
    )
    op.create_index("ix_cs_study_plan_items_id", "study_plan_items", ["id"], schema="cs")
    op.create_index("ix_cs_study_plan_items_plan_id", "study_plan_items", ["plan_id"], schema="cs")

    op.add_column(
        "interview_processes",
        sa.Column(
            "study_plan_id",
            sa.Integer(),
            sa.ForeignKey("cs.study_plans.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="organizer",
    )

    op.drop_table("plans_tags", schema="study")
    op.drop_table("tags", schema="study")
    op.drop_table("plan_items", schema="study")
    op.drop_table("plans", schema="study")
    op.drop_table("tracks", schema="study")
    op.execute("DROP SCHEMA IF EXISTS study")
