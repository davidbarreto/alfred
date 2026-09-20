"""Add core.api_requests table

One row per HTTP request to the backend, tagged with the calling service
(X-Alfred-Client header, "unknown" when absent), so Insights can chart API
usage per caller.

Revision ID: 068
Revises: 067
Create Date: 2026-09-20
"""
from alembic import op
import sqlalchemy as sa

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_requests",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client", sa.String(50), nullable=False),
        sa.Column("method", sa.String(10), nullable=False),
        sa.Column("route", sa.String(255), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        schema="core",
    )
    op.create_index("ix_api_requests_created_at_client", "api_requests", ["created_at", "client"], schema="core")


def downgrade() -> None:
    op.drop_index("ix_api_requests_created_at_client", table_name="api_requests", schema="core")
    op.drop_table("api_requests", schema="core")
