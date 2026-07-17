"""Statement imports: import_batches, import_rules, transaction import fields

Revision ID: 022
Revises: 021
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "022"
down_revision = "021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_batches",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "account_id",
            sa.Integer(),
            sa.ForeignKey("finance.accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column("stored_file", sa.String(512), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=True),
        sa.Column("period_end", sa.Date(), nullable=True),
        sa.Column("closing_balance", sa.Numeric(12, 2), nullable=True),
        sa.Column("inserted_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="finance",
    )
    op.create_table(
        "import_rules",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("pattern", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("mode", sa.String(10), nullable=False, server_default="auto"),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("merchant", sa.String(255), nullable=True),
        sa.Column(
            "category_id",
            sa.Integer(),
            sa.ForeignKey("finance.categories.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "transfer_account_id",
            sa.Integer(),
            sa.ForeignKey("finance.accounts.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        schema="finance",
    )
    op.add_column("transactions", sa.Column("bank_description", sa.Text(), nullable=True), schema="finance")
    op.add_column("transactions", sa.Column("note", sa.Text(), nullable=True), schema="finance")
    op.add_column(
        "transactions",
        sa.Column(
            "counterpart_account_id",
            sa.Integer(),
            sa.ForeignKey("finance.accounts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="finance",
    )
    op.add_column(
        "transactions",
        sa.Column(
            "import_batch_id",
            sa.Integer(),
            sa.ForeignKey("finance.import_batches.id", ondelete="SET NULL"),
            nullable=True,
        ),
        schema="finance",
    )


def downgrade() -> None:
    op.drop_column("transactions", "import_batch_id", schema="finance")
    op.drop_column("transactions", "counterpart_account_id", schema="finance")
    op.drop_column("transactions", "note", schema="finance")
    op.drop_column("transactions", "bank_description", schema="finance")
    op.drop_table("import_rules", schema="finance")
    op.drop_table("import_batches", schema="finance")
