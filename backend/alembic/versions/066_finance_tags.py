"""Add finance.tags and finance.transactions_tags

Free-form context tags for transactions (e.g. "Travel", "Work"), orthogonal to
category -- a transaction can carry several at once, unlike the exclusive
category_id. See app/features/finance/tags/tables.py.

Revision ID: 066
Revises: 065
Create Date: 2026-09-15
"""
from alembic import op
import sqlalchemy as sa

revision = "066"
down_revision = "065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tags",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.UniqueConstraint("name", name="uq_finance_tags_name"),
        schema="finance",
    )
    op.create_index("ix_finance_tags_name", "tags", ["name"], schema="finance")

    op.create_table(
        "transactions_tags",
        sa.Column(
            "transaction_id",
            sa.Integer(),
            sa.ForeignKey("finance.transactions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            sa.Integer(),
            sa.ForeignKey("finance.tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_table("transactions_tags", schema="finance")
    op.drop_index("ix_finance_tags_name", table_name="tags", schema="finance")
    op.drop_table("tags", schema="finance")
