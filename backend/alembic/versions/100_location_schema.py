"""Create the location schema and move countries and cities into it

Phase 1 of the location domain: `travel.countries` and `travel.cities` become `location.countries` and
`location.cities`, so the weather setting, everyday places and travel all share one geography. ALTER TABLE
... SET SCHEMA keeps the rows, ids, sequences, constraints and the foreign keys that point at the tables
(places, legs, trips, trip cities, links); only the schema-prefixed index names are renamed.

Revision ID: 100
Revises: 099
Create Date: 2026-11-25
"""
import os

from alembic import op
from sqlalchemy.engine import make_url

revision = "100"
down_revision = "099"
branch_labels = None
depends_on = None

_SCHEMA = "location"
_TABLES = ("countries", "cities")
# Index names that carry the schema; primary keys and foreign keys are named after the table only.
_INDEXES = (
    ("ix", "countries_id"), ("uq", "countries_name"), ("uq", "countries_code"),
    ("ix", "cities_id"), ("uq", "cities_name_country"),
)


def _rename_indexes(old: str, new: str) -> None:
    """Rename the indexes of the moved tables from `<prefix>_<old>_*` to `<prefix>_<new>_*` (they live in `new` now)."""
    for prefix, suffix in _INDEXES:
        op.execute(f"ALTER INDEX {new}.{prefix}_{old}_{suffix} RENAME TO {prefix}_{new}_{suffix}")


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {_SCHEMA}")
    for table in _TABLES:
        op.execute(f"ALTER TABLE travel.{table} SET SCHEMA {_SCHEMA}")
    _rename_indexes("travel", _SCHEMA)

    app_user = make_url(os.getenv("DATABASE_URL", "")).username
    if app_user:
        op.execute(f"GRANT USAGE ON SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA {_SCHEMA} TO {app_user}")
        op.execute(
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {app_user}"
        )
        op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA {_SCHEMA} GRANT USAGE, SELECT ON SEQUENCES TO {app_user}")


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {_SCHEMA}.{table} SET SCHEMA travel")
    _rename_indexes(_SCHEMA, "travel")
    op.execute(f"DROP SCHEMA IF EXISTS {_SCHEMA}")
