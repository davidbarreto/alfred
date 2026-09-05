"""Add organizer.interview_preferences singleton table

Stores the user's job-search preferences (work regime, target office
days/month, salary range, locations, tech stack, roles, career
objectives) so the interview insights LLM prompt can factor fit into
its recommendations, and so the portal preferences page has somewhere
to persist them.

Revision ID: 064
Revises: 063
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_regimes", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("target_office_days_per_month", sa.Float(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_max", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(10), nullable=True),
        sa.Column("locations", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("tech_stack", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("roles", ARRAY(sa.String()), nullable=False, server_default="{}"),
        sa.Column("career_objectives", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_table("interview_preferences", schema="organizer")
