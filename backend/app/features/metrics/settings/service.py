import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.metrics.settings.schemas import MetricsSettingsRead, MetricsSettingsUpdate

logger = logging.getLogger(__name__)

_KEY_PREFIX = "metrics."

# Stored as "metrics.<field>"; a missing or blank row falls back to the default.
DEFAULTS: dict[str, int | float] = {name: field.default for name, field in MetricsSettingsRead.model_fields.items()}


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class MetricsSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> MetricsSettingsRead:
        values: dict[str, int | float] = {}
        for field, default in DEFAULTS.items():
            raw = await self._settings.get_value(_key(field))
            values[field] = type(default)(raw) if raw else default
        return MetricsSettingsRead(**values)

    async def update(self, data: MetricsSettingsUpdate) -> MetricsSettingsRead:
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        for field, value in changes.items():
            await self._settings.set_value(_key(field), str(value))
        logger.info("Metrics settings updated: fields=%s", list(changes))
        return await self.get()
