"""Add unique constraint on working_memory.key

Revision ID: 019
Revises: 018
Create Date: 2026-07-11
"""

from alembic import op

revision = "019"
down_revision = "018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Guarded so a concurrent/retried "alembic upgrade head" run — which can race on this
    # DDL and lose — doesn't fail the deploy after the constraint was already committed.
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_core_working_memory_key'
            ) THEN
                ALTER TABLE core.working_memory ADD CONSTRAINT uq_core_working_memory_key UNIQUE (key);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_core_working_memory_key'
            ) THEN
                ALTER TABLE core.working_memory DROP CONSTRAINT uq_core_working_memory_key;
            END IF;
        END $$;
    """)
