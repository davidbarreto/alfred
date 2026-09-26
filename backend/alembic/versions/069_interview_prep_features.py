"""Add interview prep: stories, prep questions, candidate questions

Revision ID: 069
Revises: 068
Create Date: 2026-09-26
"""
from alembic import op
import sqlalchemy as sa

revision = "069"
down_revision = "068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_stories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("situation", sa.Text(), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("strength", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("strength BETWEEN 1 AND 5", name="ck_interview_stories_strength"),
        schema="organizer",
    )
    op.create_index("ix_interview_stories_id", "interview_stories", ["id"], schema="organizer")

    op.create_table(
        "interview_story_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["story_id"], ["organizer.interview_stories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", "tag", name="uq_story_tag"),
        schema="organizer",
    )
    op.create_index("ix_interview_story_tags_story_id", "interview_story_tags", ["story_id"], schema="organizer")
    op.create_index("ix_interview_story_tags_tag", "interview_story_tags", ["tag"], schema="organizer")

    op.create_table(
        "interview_prep_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        schema="organizer",
    )
    op.create_index("ix_interview_prep_questions_id", "interview_prep_questions", ["id"], schema="organizer")

    op.create_table(
        "interview_story_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("fit_score", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["story_id"], ["organizer.interview_stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["organizer.interview_prep_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("story_id", "question_id", name="uq_story_question"),
        sa.CheckConstraint("fit_score BETWEEN 1 AND 5", name="ck_interview_story_questions_fit_score"),
        schema="organizer",
    )
    op.create_index("ix_interview_story_questions_story_id", "interview_story_questions", ["story_id"], schema="organizer")
    op.create_index("ix_interview_story_questions_question_id", "interview_story_questions", ["question_id"], schema="organizer")

    op.create_table(
        "interview_candidate_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("text", sa.String(500), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        schema="organizer",
    )
    op.create_index("ix_interview_candidate_questions_id", "interview_candidate_questions", ["id"], schema="organizer")
    op.create_index("ix_interview_candidate_questions_category", "interview_candidate_questions", ["category"], schema="organizer")


def downgrade() -> None:
    op.drop_table("interview_candidate_questions", schema="organizer")
    op.drop_table("interview_story_questions", schema="organizer")
    op.drop_table("interview_prep_questions", schema="organizer")
    op.drop_table("interview_story_tags", schema="organizer")
    op.drop_table("interview_stories", schema="organizer")
