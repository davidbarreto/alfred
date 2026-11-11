import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.travel.settings_schemas import TravelSettingsRead, TravelSettingsUpdate

logger = logging.getLogger(__name__)

_KEY_PREFIX = "travel."
# Personal data, so it lives in the organizer namespace; travel only reads it (and still edits it via /travel/settings).
HOME_ADDRESS_KEY = "organizer.home_address"

# Stored in core.settings as "travel.<field>"; a missing row falls back to the default below.
DEFAULT_AIRPORT_BUFFER_MIN = 120
DEFAULT_HOME_TO_AIRPORT_MIN = 45
_DEFAULTS = {
    "airport_buffer_min": DEFAULT_AIRPORT_BUFFER_MIN,
    "home_to_airport_min": DEFAULT_HOME_TO_AIRPORT_MIN,
}


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class TravelSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> TravelSettingsRead:
        values: dict[str, int | str | None] = {}
        for field, default in _DEFAULTS.items():
            raw = await self._settings.get_value(_key(field))
            values[field] = int(raw) if raw else default
        values["home_address"] = await self._settings.get_value(HOME_ADDRESS_KEY) or None
        return TravelSettingsRead(**values)

    async def update(self, data: TravelSettingsUpdate) -> TravelSettingsRead:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in changes.items():
            key = HOME_ADDRESS_KEY if field == "home_address" else _key(field)
            await self._settings.set_value(key, str(value).strip())
        logger.info("Travel settings updated: fields=%s", list(changes.keys()))
        return await self.get()
