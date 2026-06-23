"""Add organizer.contacts table

Revision ID: 008
Revises: 007
Create Date: 2026-06-23
"""

from alembic import op
import sqlalchemy as sa

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(100), nullable=True),
        sa.Column("birthday", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", name="uq_contacts_provider_id"),
        schema="organizer",
    )
    op.create_index("ix_organizer_contacts_id", "contacts", ["id"], schema="organizer")


def downgrade() -> None:
    op.drop_index("ix_organizer_contacts_id", table_name="contacts", schema="organizer")
    op.drop_table("contacts", schema="organizer")
