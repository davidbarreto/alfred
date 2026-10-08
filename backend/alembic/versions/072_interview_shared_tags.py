"""Shared interview tag vocabulary for stories and prep questions

Replaces organizer.interview_story_tags (free-text rows per story) with a shared
organizer.interview_tags table plus link tables for stories and prep questions.
Existing story tags are migrated; tags differing only by case are merged.

Revision ID: 072
Revises: 071
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa

revision = "072"
down_revision = "071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        schema="organizer",
    )
    op.create_index("ix_interview_tags_id", "interview_tags", ["id"], schema="organizer")
    op.execute(
        "CREATE UNIQUE INDEX uq_interview_tags_name_lower ON organizer.interview_tags (lower(name))"
    )

    op.create_table(
        "interview_story_tag_links",
        sa.Column("story_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["story_id"], ["organizer.interview_stories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["organizer.interview_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("story_id", "tag_id"),
        schema="organizer",
    )
    op.create_index("ix_interview_story_tag_links_tag_id", "interview_story_tag_links", ["tag_id"], schema="organizer")

    op.create_table(
        "interview_question_tag_links",
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["organizer.interview_prep_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["organizer.interview_tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("question_id", "tag_id"),
        schema="organizer",
    )
    op.create_index(
        "ix_interview_question_tag_links_tag_id", "interview_question_tag_links", ["tag_id"], schema="organizer"
    )

    # Case-insensitive merge: the alphabetically first spelling becomes the canonical name.
    op.execute(
        """
        INSERT INTO organizer.interview_tags (name)
        SELECT min(tag) FROM organizer.interview_story_tags GROUP BY lower(tag)
        """
    )
    op.execute(
        """
        INSERT INTO organizer.interview_story_tag_links (story_id, tag_id)
        SELECT DISTINCT st.story_id, t.id
        FROM organizer.interview_story_tags st
        JOIN organizer.interview_tags t ON lower(t.name) = lower(st.tag)
        """
    )
    op.drop_table("interview_story_tags", schema="organizer")


def downgrade() -> None:
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
    op.execute(
        """
        INSERT INTO organizer.interview_story_tags (story_id, tag)
        SELECT l.story_id, t.name
        FROM organizer.interview_story_tag_links l
        JOIN organizer.interview_tags t ON t.id = l.tag_id
        """
    )
    op.drop_table("interview_question_tag_links", schema="organizer")
    op.drop_table("interview_story_tag_links", schema="organizer")
    op.drop_table("interview_tags", schema="organizer")
