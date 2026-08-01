"""Grant app user permissions on cs schema

Revision ID: 041
Revises: 040
Create Date: 2026-08-01
"""

import os

from alembic import op
from sqlalchemy.engine import make_url

revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None

_SCHEMA = "cs"


def upgrade() -> None:
    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if not app_user:
        return
    op.execute(f"GRANT USAGE ON SCHEMA {_SCHEMA} TO {app_user}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {_SCHEMA} TO {app_user}")
    op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {_SCHEMA} TO {app_user}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT USAGE, SELECT ON SEQUENCES TO {app_user}")


def downgrade() -> None:
    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if not app_user:
        return
    op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {_SCHEMA} FROM {app_user}")
    op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {_SCHEMA} FROM {app_user}")
    op.execute(f"REVOKE USAGE ON SCHEMA {_SCHEMA} FROM {app_user}")
