"""Add website column to organizer.contacts

Contacts only had name/email/phone/birthday. This column stores a single
profile URL (e.g. LinkedIn), synced against the Google People API's `urls`
resource so it round-trips through the existing write-through Contacts sync.

Revision ID: 062
Revises: 061
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "062"
down_revision = "061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "contacts",
        sa.Column("website", sa.String(500), nullable=True),
        schema="organizer",
    )


def downgrade() -> None:
    op.drop_column("contacts", "website", schema="organizer")
