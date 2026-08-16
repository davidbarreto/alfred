"""Add auto_mirror_transfers to finance.accounts and generated_from_transaction_id to finance.transactions

Some accounts (e.g. a bank's linked savings sub-account) never produce their own
statement -- only transfers to/from them appear on the main account's statement,
plus a periodic balance. Marking such an account auto_mirror_transfers=True makes
a transfer that targets it (via Transaction.counterpart_account_id) also create a
real, visible mirror transaction row in that account, tagged via
generated_from_transaction_id. The mirror carries no balance effect of its own --
the source leg's existing counterpart-credit already moves the money -- it only
makes the transfer visible in that account's own transaction list. ondelete=CASCADE
so deleting the source leg cleans up its mirror automatically.

Revision ID: 055
Revises: 054
Create Date: 2026-08-16
"""
from alembic import op
import sqlalchemy as sa

revision = "055"
down_revision = "054"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "accounts",
        sa.Column("auto_mirror_transfers", sa.Boolean(), nullable=False, server_default=sa.false()),
        schema="finance",
    )
    op.alter_column("accounts", "auto_mirror_transfers", server_default=None, schema="finance")
    op.add_column(
        "transactions",
        sa.Column("generated_from_transaction_id", sa.Integer(), nullable=True),
        schema="finance",
    )
    op.create_foreign_key(
        "fk_transactions_generated_from_transaction_id",
        "transactions",
        "transactions",
        ["generated_from_transaction_id"],
        ["id"],
        source_schema="finance",
        referent_schema="finance",
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_transactions_generated_from_transaction_id", "transactions", schema="finance", type_="foreignkey"
    )
    op.drop_column("transactions", "generated_from_transaction_id", schema="finance")
    op.drop_column("accounts", "auto_mirror_transfers", schema="finance")
