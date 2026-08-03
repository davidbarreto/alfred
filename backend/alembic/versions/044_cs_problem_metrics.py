"""Add provider metrics columns to cs.problems and cs.platforms

Revision ID: 044
Revises: 043
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("problems", sa.Column("acceptance_rate", sa.Float(), nullable=True), schema="cs")
    op.add_column("problems", sa.Column("solved_count", sa.Integer(), nullable=True), schema="cs")
    op.add_column("problems", sa.Column("likes", sa.Integer(), nullable=True), schema="cs")
    op.add_column("problems", sa.Column("dislikes", sa.Integer(), nullable=True), schema="cs")
    op.add_column(
        "problems", sa.Column("metrics_updated_at", sa.DateTime(timezone=True), nullable=True), schema="cs"
    )
    op.add_column(
        "platforms", sa.Column("metrics_refreshed_at", sa.DateTime(timezone=True), nullable=True), schema="cs"
    )


def downgrade() -> None:
    op.drop_column("platforms", "metrics_refreshed_at", schema="cs")
    op.drop_column("problems", "metrics_updated_at", schema="cs")
    op.drop_column("problems", "dislikes", schema="cs")
    op.drop_column("problems", "likes", schema="cs")
    op.drop_column("problems", "solved_count", schema="cs")
    op.drop_column("problems", "acceptance_rate", schema="cs")
