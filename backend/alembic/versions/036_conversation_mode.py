"""Add conversation_threads.mode and make scenario nullable

Free conversation now runs as a thread too (previously it only lived in working
memory), so a thread needs to say which mode it is, and `scenario` becomes
optional — it holds the roleplay scenario or the free-conversation topic, both
of which may be absent for a topic-less chat.

Revision ID: 036
Revises: 035
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversation_threads",
        sa.Column("mode", sa.String(20), nullable=False, server_default="roleplay"),
        schema="language",
    )
    op.alter_column("conversation_threads", "scenario", nullable=True, schema="language")


def downgrade() -> None:
    # Free-conversation threads have no scenario; give them one so the column can go
    # back to NOT NULL.
    op.execute(
        "UPDATE language.conversation_threads SET scenario = '(no scenario)' WHERE scenario IS NULL"
    )
    op.alter_column("conversation_threads", "scenario", nullable=False, schema="language")
    op.drop_column("conversation_threads", "mode", schema="language")
