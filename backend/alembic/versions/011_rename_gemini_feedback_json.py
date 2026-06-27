"""rename gemini_feedback_json to ai_feedback_json

Revision ID: 011
Revises: 010
Create Date: 2026-06-27
"""

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("sessions", "gemini_feedback_json", new_column_name="ai_feedback_json", schema="language")


def downgrade() -> None:
    op.alter_column("sessions", "ai_feedback_json", new_column_name="gemini_feedback_json", schema="language")
