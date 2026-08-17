"""Add finance.installment_plans, transactions.installment_plan_id, import_rules.installment_plan_id

Some purchases are financed in installments -- a card statement (ActivoBank
"fracionado") or a lender like Cetelem/Nubank debits one monthly amount over
several months instead of the full price up front. installment_plans tracks
each plan's total vs. captured installments (captured is derived live by
counting linked transactions, not stored) plus cumulative interest/duty paid.

transactions.installment_plan_id links every transaction belonging to a plan
(including a superseded lump-sum original, set to 0 with a note once its
real monthly installments are known) back to that plan.

import_rules.installment_plan_id lets an ordinary import rule (the same
mechanism that already auto-assigns category/type by description match)
auto-link a future imported transaction to a plan -- this is how both
ActivoBank's own recurring Capital-installment rows and manually-created
plans (Cetelem, Nubank, ...) get their transactions tagged, with no
provider-specific matching logic.

Revision ID: 056
Revises: 055
Create Date: 2026-08-17
"""
from alembic import op
import sqlalchemy as sa

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "installment_plans",
        sa.Column("id", sa.Integer, primary_key=True, index=True),
        sa.Column(
            "account_id",
            sa.Integer,
            sa.ForeignKey("finance.accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("total_installments", sa.Integer, nullable=False),
        sa.Column("plan_ref", sa.String(20), nullable=True),
        sa.Column("opened_date", sa.Date, nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("total_interest_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("total_duty_paid", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), nullable=False),
        schema="finance",
    )
    op.create_index(
        "ux_installment_plans_open_desc",
        "installment_plans",
        ["account_id", "description"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("status = 'open'"),
    )

    op.add_column(
        "transactions",
        sa.Column("installment_plan_id", sa.Integer(), nullable=True),
        schema="finance",
    )
    op.create_foreign_key(
        "fk_transactions_installment_plan_id",
        "transactions",
        "installment_plans",
        ["installment_plan_id"],
        ["id"],
        source_schema="finance",
        referent_schema="finance",
        ondelete="SET NULL",
    )

    op.add_column(
        "import_rules",
        sa.Column("installment_plan_id", sa.Integer(), nullable=True),
        schema="finance",
    )
    op.create_foreign_key(
        "fk_import_rules_installment_plan_id",
        "import_rules",
        "installment_plans",
        ["installment_plan_id"],
        ["id"],
        source_schema="finance",
        referent_schema="finance",
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_import_rules_installment_plan_id", "import_rules", schema="finance", type_="foreignkey"
    )
    op.drop_column("import_rules", "installment_plan_id", schema="finance")

    op.drop_constraint(
        "fk_transactions_installment_plan_id", "transactions", schema="finance", type_="foreignkey"
    )
    op.drop_column("transactions", "installment_plan_id", schema="finance")

    op.drop_index("ux_installment_plans_open_desc", table_name="installment_plans", schema="finance")
    op.drop_table("installment_plans", schema="finance")
