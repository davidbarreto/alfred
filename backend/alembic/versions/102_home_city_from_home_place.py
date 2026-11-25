"""Home is one place: the home city is the Home place's city, the travel.home_city_id setting goes

Phase 3 of the location domain. Data only.

Upgrade: when the `travel.home_city_id` setting names an existing city and a Home place exists, the Home place takes
that city (migration 101 already put it there, so this is usually a no-op). Then the setting is deleted. A setting with
no Home place to receive it is dropped too: the home city is now "the Home place's city", and there is none.

Downgrade: the setting is written back from the Home place's city (nothing is written when there is no Home place).

Revision ID: 102
Revises: 101
Create Date: 2026-11-25
"""
from alembic import op

revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE location.places p SET city_id = c.id, updated_at = now() "
        "FROM core.settings s JOIN location.cities c ON s.value ~ '^[0-9]+$' AND c.id = s.value::int "
        "WHERE s.key = 'travel.home_city_id' AND p.kind = 'home' AND p.city_id <> c.id"
    )
    op.execute("DELETE FROM core.settings WHERE key = 'travel.home_city_id'")


def downgrade() -> None:
    op.execute(
        "INSERT INTO core.settings (key, value) "
        "SELECT 'travel.home_city_id', city_id::text FROM location.places WHERE kind = 'home' "
        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value"
    )
