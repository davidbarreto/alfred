"""Restrict account deletion when transactions/recurring/import history exists

Deleting an account used to CASCADE-delete every transaction, recurring
transaction, and import batch tied to it -- silent and irreversible. Changed
to RESTRICT so the delete is blocked (and can be surfaced as a clear error)
instead of quietly destroying financial history.

Revision ID: 024
Revises: 023
Create Date: 2026-07-18
"""
from alembic import op

revision = "024"
down_revision = "023"
branch_labels = None
depends_on = None

# (table, constraint_name, column) -- constraint names are Postgres's default
# auto-generated "<table>_<column>_fkey", since the original FKs were declared
# inline without an explicit name.
_ACCOUNT_FKS = [
    ("transactions", "transactions_account_id_fkey", "account_id"),
    ("recurring_transactions", "recurring_transactions_account_id_fkey", "account_id"),
    ("import_batches", "import_batches_account_id_fkey", "account_id"),
]


def upgrade() -> None:
    for table, constraint, column in _ACCOUNT_FKS:
        op.drop_constraint(constraint, table, schema="finance", type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "accounts",
            [column],
            ["id"],
            source_schema="finance",
            referent_schema="finance",
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    for table, constraint, column in _ACCOUNT_FKS:
        op.drop_constraint(constraint, table, schema="finance", type_="foreignkey")
        op.create_foreign_key(
            constraint,
            table,
            "accounts",
            [column],
            ["id"],
            source_schema="finance",
            referent_schema="finance",
            ondelete="CASCADE",
        )
