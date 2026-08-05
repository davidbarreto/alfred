"""Create integration.embedding_calls log table

Revision ID: 046
Revises: 045
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "046"
down_revision = "045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embedding_calls",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature", sa.String(100), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=False),
        sa.Column("source_types", JSONB(), nullable=True),
        sa.Column("top_k", sa.Integer(), nullable=False),
        sa.Column("threshold", sa.Float(), nullable=False),
        sa.Column("results", JSONB(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        schema="integration",
    )
    op.create_index("ix_integration_embedding_calls_id", "embedding_calls", ["id"], schema="integration")
    op.create_index("ix_integration_embedding_calls_feature", "embedding_calls", ["feature"], schema="integration")
    op.create_index("ix_integration_embedding_calls_created_at", "embedding_calls", ["created_at"], schema="integration")


def downgrade() -> None:
    op.drop_index("ix_integration_embedding_calls_created_at", table_name="embedding_calls", schema="integration")
    op.drop_index("ix_integration_embedding_calls_feature", table_name="embedding_calls", schema="integration")
    op.drop_index("ix_integration_embedding_calls_id", table_name="embedding_calls", schema="integration")
    op.drop_table("embedding_calls", schema="integration")
