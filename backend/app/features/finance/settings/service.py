import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.finance.settings.schemas import FinanceSettingsRead, FinanceSettingsUpdate

logger = logging.getLogger(__name__)

CYCLE_START_DAY_KEY = "finance.cycle_start_day"
_DEFAULT_CYCLE_START_DAY = 1


class FinanceSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> FinanceSettingsRead:
        raw = await self._settings.get_value(CYCLE_START_DAY_KEY)
        cycle_start_day = int(raw) if raw is not None else _DEFAULT_CYCLE_START_DAY
        return FinanceSettingsRead(cycle_start_day=cycle_start_day)

    async def get_cycle_start_day(self) -> int:
        settings = await self.get()
        return settings.cycle_start_day

    async def update(self, data: FinanceSettingsUpdate) -> FinanceSettingsRead:
        await self._settings.set_value(CYCLE_START_DAY_KEY, str(data.cycle_start_day))
        logger.info("Finance settings updated: cycle_start_day=%d", data.cycle_start_day)
        return FinanceSettingsRead(cycle_start_day=data.cycle_start_day)
