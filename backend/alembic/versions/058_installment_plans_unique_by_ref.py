"""Fix finance.installment_plans open-plan uniqueness: key by plan_ref, not description

Multiple distinct plans can share an identical description -- e.g. several
separate Revolut top-ups in the same statement, each split into its own
installment plan, all read "COMPRA 4681 Revolut 9424 Dublin". The original
unique index on (account_id, description) rejected the second such plan
with an IntegrityError, which silently aborted the rest of that PDF
import's plan-creation loop (each plan's create() commits individually --
confirmed against a real import: only the first 2 of 9 plans were created
before the 3rd hit this collision and crashed the request, leaving the
remaining 7 plans -- including the one the user was specifically waiting on
to supersede an existing transaction -- never even attempted).

plan_ref is the correct uniqueness key for a PDF-derived plan (assigned by
the bank, genuinely unique). description remains the key for a manually-
created plan (Cetelem/Nubank), which has no plan_ref at all -- so this
becomes two partial unique indexes instead of one, split by whether
plan_ref is set.

Revision ID: 058
Revises: 057
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "058"
down_revision = "057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ux_installment_plans_open_desc", table_name="installment_plans", schema="finance")
    op.create_index(
        "ux_installment_plans_open_plan_ref",
        "installment_plans",
        ["account_id", "plan_ref"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("status = 'open' AND plan_ref IS NOT NULL"),
    )
    op.create_index(
        "ux_installment_plans_open_desc",
        "installment_plans",
        ["account_id", "description"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("status = 'open' AND plan_ref IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_installment_plans_open_desc", table_name="installment_plans", schema="finance")
    op.drop_index("ux_installment_plans_open_plan_ref", table_name="installment_plans", schema="finance")
    op.create_index(
        "ux_installment_plans_open_desc",
        "installment_plans",
        ["account_id", "description"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("status = 'open'"),
    )
