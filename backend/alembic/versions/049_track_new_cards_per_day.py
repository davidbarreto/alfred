"""Add new_cards_per_day column to language.tracks

Caps how many never-reviewed (state="new") chunks can enter recognition
rotation per day, independent of daily_quota (which caps the whole batch
size, new + review combined). Without this, bulk-importing a large chunk
list makes all of them due=now at once, so daily_quota alone still shows
a huge, unthrottled "due" backlog on day one.

Revision ID: 049
Revises: 048
Create Date: 2026-08-10
"""
from alembic import op
import sqlalchemy as sa

revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tracks",
        sa.Column("new_cards_per_day", sa.Integer(), nullable=False, server_default="10"),
        schema="language",
    )


def downgrade() -> None:
    op.drop_column("tracks", "new_cards_per_day", schema="language")
