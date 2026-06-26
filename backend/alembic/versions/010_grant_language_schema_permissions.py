"""Grant app user permissions on language schema

Revision ID: 010
Revises: 009
Create Date: 2026-06-26
"""

import os

from alembic import op
from sqlalchemy.engine import make_url

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if not app_user:
        return
    op.execute(f"GRANT USAGE ON SCHEMA language TO {app_user}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA language TO {app_user}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA language TO {app_user}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA language GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA language GRANT USAGE, SELECT ON SEQUENCES TO {app_user}")


def downgrade() -> None:
    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if not app_user:
        return
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA language FROM {app_user}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA language FROM {app_user}")
    op.execute(f"REVOKE USAGE ON SCHEMA language FROM {app_user}")
