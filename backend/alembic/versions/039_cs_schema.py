"""Create cs schema with platforms, tags, problems, problems_tags, submissions, study_plans, study_plan_items

Revision ID: 039
Revises: 038
Create Date: 2026-07-31
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS cs")

    op.create_table(
        "platforms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("handle", sa.String(100), nullable=True),
        sa.Column("sync_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_submission_external_id", sa.String(50), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=True),
        sa.Column("max_rating", sa.Integer(), nullable=True),
        sa.Column("rank", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_cs_platforms_code"),
        schema="cs",
    )
    op.create_index("ix_cs_platforms_id", "platforms", ["id"], schema="cs")

    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_cs_tags_name"),
        schema="cs",
    )
    op.create_index("ix_cs_tags_id", "tags", ["id"], schema="cs")

    op.create_table(
        "problems",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("url", sa.String(500), nullable=True),
        sa.Column("difficulty_raw", sa.String(50), nullable=True),
        sa.Column("difficulty", sa.String(10), nullable=True),
        sa.Column("tags_raw", JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["platform_id"], ["cs.platforms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_id", "external_id", name="uq_cs_problems_platform_external_id"),
        schema="cs",
    )
    op.create_index("ix_cs_problems_id", "problems", ["id"], schema="cs")
    op.create_index("ix_cs_problems_platform_id", "problems", ["platform_id"], schema="cs")

    op.create_table(
        "problems_tags",
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["problem_id"], ["cs.problems.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["cs.tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("problem_id", "tag_id"),
        schema="cs",
    )

    op.create_table(
        "submissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform_id", sa.Integer(), nullable=False),
        sa.Column("problem_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sa.String(50), nullable=False),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("verdict_raw", sa.String(50), nullable=True),
        sa.Column("language", sa.String(30), nullable=True),
        sa.Column("language_raw", sa.String(100), nullable=True),
        sa.Column("source_method", sa.String(20), nullable=False, server_default="api_sync"),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["platform_id"], ["cs.platforms.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["cs.problems.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("platform_id", "external_id", name="uq_cs_submissions_platform_external_id"),
        schema="cs",
    )
    op.create_index("ix_cs_submissions_id", "submissions", ["id"], schema="cs")
    op.create_index("ix_cs_submissions_platform_id", "submissions", ["platform_id"], schema="cs")
    op.create_index("ix_cs_submissions_problem_id", "submissions", ["problem_id"], schema="cs")
    op.create_index("ix_cs_submissions_submitted_at", "submissions", ["submitted_at"], schema="cs")

    op.create_table(
        "study_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cadence", sa.String(20), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
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
        sa.Column("is_done", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["plan_id"], ["cs.study_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["problem_id"], ["cs.problems.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        schema="cs",
    )
    op.create_index("ix_cs_study_plan_items_id", "study_plan_items", ["id"], schema="cs")
    op.create_index("ix_cs_study_plan_items_plan_id", "study_plan_items", ["plan_id"], schema="cs")


def downgrade() -> None:
    op.drop_table("study_plan_items", schema="cs")
    op.drop_table("study_plans", schema="cs")
    op.drop_table("submissions", schema="cs")
    op.drop_table("problems_tags", schema="cs")
    op.drop_table("problems", schema="cs")
    op.drop_table("tags", schema="cs")
    op.drop_table("platforms", schema="cs")
    op.execute("DROP SCHEMA IF EXISTS cs")
