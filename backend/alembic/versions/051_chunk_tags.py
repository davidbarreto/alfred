"""Add language.tags + chunks_tags, and tracks.active_tags

Lets vocabulary chunks be freely tagged into overlapping practice groups
(e.g. "Food", "Work", "A1 collocations") so a review session can be
narrowed to a subset instead of pulling from the whole due backlog.
tracks.active_tags stores which tag(s) are currently selected for a
track's recognition batch (empty = unfiltered, same as before this
migration).

Unlike organizer.tags, language.tags has no provider_id scoping column:
chunks have no external write-through provider, and Alfred is
single-tenant, so tag names are just globally unique within this schema.

Revision ID: 051
Revises: 050
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "051"
down_revision = "050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_language_tags_name"),
        schema="language",
    )
    op.create_index("ix_language_tags_id", "tags", ["id"], schema="language")

    op.create_table(
        "chunks_tags",
        sa.Column("chunk_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["chunk_id"], ["language.chunks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tag_id"], ["language.tags.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("chunk_id", "tag_id"),
        schema="language",
    )

    op.add_column(
        "tracks",
        sa.Column(
            "active_tags", ARRAY(sa.String()), nullable=False, server_default="{}"
        ),
        schema="language",
    )


def downgrade() -> None:
    op.drop_column("tracks", "active_tags", schema="language")
    op.drop_table("chunks_tags", schema="language")
    op.drop_index("ix_language_tags_id", table_name="tags", schema="language")
    op.drop_table("tags", schema="language")
