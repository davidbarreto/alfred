import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.briefing.settings_schemas import BriefingSettingsRead, BriefingSettingsUpdate
from app.features.core.settings.service import SettingService

logger = logging.getLogger(__name__)

_KEY_PREFIX = "briefing."

# Stored in core.settings as "briefing.<field>"; a missing or blank row falls back to the default.
DEFAULTS: dict[str, int] = {name: field.default for name, field in BriefingSettingsRead.model_fields.items()}


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class BriefingSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> BriefingSettingsRead:
        values: dict[str, int] = {}
        for field, default in DEFAULTS.items():
            raw = await self._settings.get_value(_key(field))
            values[field] = int(raw) if raw else default
        return BriefingSettingsRead(**values)

    async def update(self, data: BriefingSettingsUpdate) -> BriefingSettingsRead:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in changes.items():
            await self._settings.set_value(_key(field), str(value))
        logger.info("Briefing settings updated: fields=%s", list(changes))
        return await self.get()
