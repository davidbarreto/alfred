"""Rename monitoring schema and tables to watcher

Revision ID: 018
Revises: 017
Create Date: 2026-07-11
"""

from alembic import op
import sqlalchemy as sa

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Rename monitoring schema to watcher
    op.execute("ALTER SCHEMA monitoring RENAME TO watcher")

    # Update unique constraint name
    op.execute("ALTER TABLE watcher.configs RENAME CONSTRAINT uq_monitoring_configs_name TO uq_watcher_configs_name")


def downgrade() -> None:
    # Rename watcher schema back to monitoring
    op.execute("ALTER SCHEMA watcher RENAME TO monitoring")

    # Rename unique constraint back
    op.execute("ALTER TABLE monitoring.configs RENAME CONSTRAINT uq_watcher_configs_name TO uq_monitoring_configs_name")
