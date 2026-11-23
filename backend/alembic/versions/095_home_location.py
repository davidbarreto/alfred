"""Home is a location: the home address moves out of the travel settings

Data only. The `organizer.home_address` setting becomes the address of the Home location (`organizer.locations`,
kind `home`), then the setting is deleted. An existing home location keeps its own address (it only gets the
setting's when it has none); a location already named "Home" becomes the home; otherwise a "Home" location is
created, with no address when the setting was never set.

Downgrade writes the Home location's address back into the setting and keeps the location (it may have been
created or edited by hand since).

Revision ID: 095
Revises: 094
Create Date: 2026-11-23
"""
from alembic import op

revision = "095"
down_revision = "094"
branch_labels = None
depends_on = None

_SETTING_KEY = "organizer.home_address"
_SETTING_ADDRESS = f"(SELECT nullif(trim(value), '') FROM core.settings WHERE key = '{_SETTING_KEY}')"


def upgrade() -> None:
    op.execute(f"""
        UPDATE organizer.locations SET address = {_SETTING_ADDRESS}, updated_at = now()
        WHERE kind = 'home' AND address IS NULL
    """)
    op.execute(f"""
        UPDATE organizer.locations SET kind = 'home', address = coalesce(address, {_SETTING_ADDRESS}), updated_at = now()
        WHERE lower(name) = 'home' AND NOT EXISTS (SELECT 1 FROM organizer.locations WHERE kind = 'home')
    """)
    op.execute(f"""
        INSERT INTO organizer.locations (name, kind, address)
        SELECT 'Home', 'home', {_SETTING_ADDRESS}
        WHERE NOT EXISTS (SELECT 1 FROM organizer.locations WHERE kind = 'home')
    """)
    op.execute(f"DELETE FROM core.settings WHERE key = '{_SETTING_KEY}'")


def downgrade() -> None:
    op.execute(f"""
        INSERT INTO core.settings (key, value)
        SELECT '{_SETTING_KEY}', address FROM organizer.locations WHERE kind = 'home' AND address IS NOT NULL
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
    """)
