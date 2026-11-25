import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.study.settings.schemas import StudySettingsRead, StudySettingsUpdate

logger = logging.getLogger(__name__)

MAX_ACTIVE_PLANS_KEY = "study.max_active_plans"
# A missing or blank row falls back to the default.
DEFAULTS = {"max_active_plans": 3}


class StudySettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> StudySettingsRead:
        raw = await self._settings.get_value(MAX_ACTIVE_PLANS_KEY)
        max_active_plans = int(raw) if raw else DEFAULTS["max_active_plans"]
        return StudySettingsRead(max_active_plans=max_active_plans)

    async def get_max_active_plans(self) -> int:
        settings = await self.get()
        return settings.max_active_plans

    async def update(self, data: StudySettingsUpdate) -> StudySettingsRead:
        await self._settings.set_value(MAX_ACTIVE_PLANS_KEY, str(data.max_active_plans))
        logger.info("Study settings updated: max_active_plans=%d", data.max_active_plans)
        return StudySettingsRead(max_active_plans=data.max_active_plans)
