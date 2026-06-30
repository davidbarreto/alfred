"""Grant app user permissions on core schemas

Revision ID: 012
Revises: 011
Create Date: 2026-06-30
"""

import os

from alembic import op
from sqlalchemy.engine import make_url

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None

_SCHEMAS = ["core", "organizer", "monitoring", "finance", "integration"]


def upgrade() -> None:
    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if not app_user:
        return
    for schema in _SCHEMAS:
        op.execute(f"GRANT USAGE ON SCHEMA {schema} TO {app_user}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {schema} TO {app_user}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {schema} TO {app_user}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}")
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} GRANT USAGE, SELECT ON SEQUENCES TO {app_user}")


def downgrade() -> None:
    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if not app_user:
        return
    for schema in _SCHEMAS:
        op.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA {schema} FROM {app_user}")
        op.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA {schema} FROM {app_user}")
        op.execute(f"REVOKE USAGE ON SCHEMA {schema} FROM {app_user}")
