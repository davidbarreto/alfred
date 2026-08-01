"""Widen cs.problems.external_id to fit long LeetCode title slugs

Revision ID: 043
Revises: 042
Create Date: 2026-08-01
"""
from alembic import op
import sqlalchemy as sa

revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "problems",
        "external_id",
        existing_type=sa.String(50),
        type_=sa.String(255),
        existing_nullable=False,
        schema="cs",
    )


def downgrade() -> None:
    op.alter_column(
        "problems",
        "external_id",
        existing_type=sa.String(255),
        type_=sa.String(50),
        existing_nullable=False,
        schema="cs",
    )
