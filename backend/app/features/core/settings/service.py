import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.repository import SettingRepository
from app.features.core.settings.schemas import SettingRead

logger = logging.getLogger(__name__)


class SettingService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = SettingRepository(session)

    async def get_value(self, key: str, default: str | None = None) -> str | None:
        setting = await self._repo.get(key)
        if setting is None:
            logger.debug("Setting read: key=%s not found", key)
            return default
        return setting.value

    async def set_value(self, key: str, value: str) -> SettingRead:
        setting = await self._repo.set(key, value)
        logger.info("Setting updated: key=%s", key)
        return SettingRead.model_validate(setting)
