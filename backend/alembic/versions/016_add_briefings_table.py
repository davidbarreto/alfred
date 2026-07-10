"""Add core.briefings table for saved daily briefing texts

Revision ID: 016
Revises: 015
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "briefings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("date", name="uq_briefings_date"),
        schema="core",
    )
    op.create_index("ix_core_briefings_id", "briefings", ["id"], schema="core")
    op.create_index("ix_core_briefings_date", "briefings", ["date"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_core_briefings_date", table_name="briefings", schema="core")
    op.drop_index("ix_core_briefings_id", table_name="briefings", schema="core")
    op.drop_table("briefings", schema="core")
