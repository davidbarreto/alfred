import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.finance.settings.schemas import (
    DEFAULT_IMPORT_KNN_LIMIT,
    DEFAULT_IMPORT_KNN_MIN_VOTE,
    DEFAULT_IMPORT_KNN_THRESHOLD,
    FinanceSettingsRead,
    FinanceSettingsUpdate,
)

logger = logging.getLogger(__name__)

CYCLE_START_DAY_KEY = "finance.cycle_start_day"
# Stored as "finance.<field>"; a missing or blank row falls back to the default.
DEFAULTS: dict[str, int | float] = {
    "cycle_start_day": 1,
    "import_knn_limit": DEFAULT_IMPORT_KNN_LIMIT,
    "import_knn_threshold": DEFAULT_IMPORT_KNN_THRESHOLD,
    "import_knn_min_vote": DEFAULT_IMPORT_KNN_MIN_VOTE,
}


def _key(field: str) -> str:
    return f"finance.{field}"


class FinanceSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> FinanceSettingsRead:
        values: dict[str, int | float] = {}
        for field, default in DEFAULTS.items():
            raw = await self._settings.get_value(_key(field))
            values[field] = type(default)(raw) if raw else default
        return FinanceSettingsRead(**values)

    async def get_cycle_start_day(self) -> int:
        settings = await self.get()
        return settings.cycle_start_day

    async def update(self, data: FinanceSettingsUpdate) -> FinanceSettingsRead:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in changes.items():
            await self._settings.set_value(_key(field), str(value))
        logger.info("Finance settings updated: fields=%s", list(changes))
        return await self.get()
