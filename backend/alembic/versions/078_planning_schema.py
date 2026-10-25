"""Create planning schema with saved day plans

planning.day_plans stores the plan a user and an LLM client agree on for a date. Saving a date
again archives the previous version (archived_at) and inserts the next one; a partial unique
index guarantees one active plan per date.

Revision ID: 078
Revises: 077
Create Date: 2026-10-25
"""
import os

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine import make_url

revision = "078"
down_revision = "077"
branch_labels = None
depends_on = None

_SCHEMA = "planning"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")

    op.create_table(
        "day_plans",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("items", postgresql.JSONB(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("plan_date", "version", name="uq_day_plans_date_version"),
        sa.CheckConstraint("source IN ('mcp', 'portal')", name="ck_day_plans_source"),
        sa.CheckConstraint("version >= 1", name="ck_day_plans_version"),
        schema=_SCHEMA,
    )
    op.create_index("ix_day_plans_id", "day_plans", ["id"], schema=_SCHEMA)
    op.create_index(
        "uq_day_plans_active_date",
        "day_plans",
        ["plan_date"],
        unique=True,
        schema=_SCHEMA,
        postgresql_where=sa.text("archived_at IS NULL"),
    )

    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if app_user:
        op.execute(f"GRANT USAGE ON SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT USAGE, SELECT ON SEQUENCES TO {app_user}")


def downgrade() -> None:
    op.drop_index("uq_day_plans_active_date", table_name="day_plans", schema=_SCHEMA)
    op.drop_index("ix_day_plans_id", table_name="day_plans", schema=_SCHEMA)
    op.drop_table("day_plans", schema=_SCHEMA)
    op.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA}")
