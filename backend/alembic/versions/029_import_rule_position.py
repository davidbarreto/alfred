"""Add import_rules.position for user-controlled match precedence

Revision ID: 029
Revises: 028
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "import_rules",
        sa.Column("position", sa.Integer(), nullable=True),
        schema="finance",
    )
    # Backfill using id order -- this is exactly the order categorization matching
    # already used (oldest rule wins ties), so existing precedence is preserved until
    # someone explicitly reorders.
    op.execute("UPDATE finance.import_rules SET position = id")
    op.alter_column("import_rules", "position", nullable=False, schema="finance")


def downgrade() -> None:
    op.drop_column("import_rules", "position", schema="finance")
