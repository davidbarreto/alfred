"""Replace generated_from_transaction_id with counterpart_transaction_id on finance.transactions

Both generated_from_transaction_id (mirror -> source, see Account.auto_mirror_transfers)
and the "confirmed match" concept (see TransactionService.link_transfer) point one
transaction at another specific transaction -- the only real difference was delete
behaviour (CASCADE for a mirror, since it's a pure synthetic echo with no independent
meaning, vs SET NULL for a confirmed real-leg match, since deleting one real leg must
never delete the other). Standardizing on SET NULL for both and merging into a single
counterpart_transaction_id column removes that duplication -- "is this row a mirror"
is already answered independently by Transaction.source == 'auto_transfer'. A mirror's
own row now also gets a mutual counterpart_transaction_id pointing back at its source
(previously only the reverse direction was recorded), and the source leg's
counterpart_transaction_id points at its mirror, which additionally makes that leg
count as a confirmed transfer (excluded from spend/counted in net worth) the same way
a manually confirmed Find Match link does -- a real mirror row is at least as strong
evidence as a user confirmation.

Trade-off accepted: deleting a source transaction no longer cascades to delete its
mirror at the DB level -- the mirror is left orphaned (counterpart_transaction_id set
NULL, but otherwise a normal-looking row) instead of being cleaned up automatically.
Expected to be rare enough not to need explicit application-level cleanup for now.

Revision ID: 060
Revises: 059
Create Date: 2026-08-20
"""
from alembic import op
import sqlalchemy as sa

revision = "060"
down_revision = "059"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("counterpart_transaction_id", sa.Integer(), nullable=True),
        schema="finance",
    )
    op.execute(
        "UPDATE finance.transactions SET counterpart_transaction_id = generated_from_transaction_id "
        "WHERE generated_from_transaction_id IS NOT NULL"
    )
    op.drop_constraint(
        "fk_transactions_generated_from_transaction_id", "transactions", schema="finance", type_="foreignkey"
    )
    op.drop_column("transactions", "generated_from_transaction_id", schema="finance")
    op.create_foreign_key(
        "fk_transactions_counterpart_transaction_id",
        "transactions",
        "transactions",
        ["counterpart_transaction_id"],
        ["id"],
        source_schema="finance",
        referent_schema="finance",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("generated_from_transaction_id", sa.Integer(), nullable=True),
        schema="finance",
    )
    op.execute(
        "UPDATE finance.transactions SET generated_from_transaction_id = counterpart_transaction_id "
        "WHERE source = 'auto_transfer'"
    )
    op.drop_constraint(
        "fk_transactions_counterpart_transaction_id", "transactions", schema="finance", type_="foreignkey"
    )
    op.drop_column("transactions", "counterpart_transaction_id", schema="finance")
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
