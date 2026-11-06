"""Let budget_targets point at a tag instead of a category

A tag budget is versioned per cycle exactly like a category budget. Transactions carrying a
budgeted tag count toward the tag's budget instead of their category's. Exactly one of
category_id / tag_id is set. Closed (historic) tag targets are removed with their tag; a tag
with an open target is refused at the service layer.

Revision ID: 083
Revises: 082
Create Date: 2026-11-06
"""
from alembic import op
import sqlalchemy as sa

revision = "083"
down_revision = "082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("budget_targets", "category_id", existing_type=sa.Integer(), nullable=True, schema="finance")
    op.add_column(
        "budget_targets",
        sa.Column("tag_id", sa.Integer(), sa.ForeignKey("finance.tags.id", ondelete="CASCADE"), nullable=True),
        schema="finance",
    )
    op.create_check_constraint(
        "ck_budget_targets_one_subject",
        "budget_targets",
        "(category_id IS NULL) <> (tag_id IS NULL)",
        schema="finance",
    )
    op.create_index(
        "ux_budget_targets_tag_open",
        "budget_targets",
        ["tag_id"],
        unique=True,
        schema="finance",
        postgresql_where=sa.text("effective_to IS NULL AND tag_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_budget_targets_tag_open", table_name="budget_targets", schema="finance")
    op.execute("DELETE FROM finance.budget_targets WHERE tag_id IS NOT NULL")
    op.drop_constraint("ck_budget_targets_one_subject", "budget_targets", schema="finance", type_="check")
    op.drop_column("budget_targets", "tag_id", schema="finance")
    op.alter_column("budget_targets", "category_id", existing_type=sa.Integer(), nullable=False, schema="finance")
