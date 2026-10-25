import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.planning.schemas import DEFAULT_WORKDAYS, PlanningSettingsRead, PlanningSettingsUpdate

logger = logging.getLogger(__name__)

_KEY_PREFIX = "planning."

# Generic defaults; nothing personal is seeded. A missing or blank row means "use the default" (unset).
DEFAULT_WORK_TARGET_MINUTES = 480
DEFAULT_WORK_TAG = "work"
DEFAULT_OFFICE_TAG = "office"


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class PlanningSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)

    async def get(self) -> PlanningSettingsRead:
        raw = {field: await self._settings.get_value(_key(field)) for field in PlanningSettingsRead.model_fields}
        return PlanningSettingsRead(
            wake_time=raw["wake_time"] or None,
            sleep_time=raw["sleep_time"] or None,
            work_target_minutes=int(raw["work_target_minutes"]) if raw["work_target_minutes"] else DEFAULT_WORK_TARGET_MINUTES,
            preferred_work_windows=json.loads(raw["preferred_work_windows"]) if raw["preferred_work_windows"] else [],
            workdays=json.loads(raw["workdays"]) if raw["workdays"] else list(DEFAULT_WORKDAYS),
            work_tag=raw["work_tag"] or DEFAULT_WORK_TAG,
            office_tag=raw["office_tag"] or DEFAULT_OFFICE_TAG,
            office_days_per_week=int(raw["office_days_per_week"]) if raw["office_days_per_week"] else None,
            office_min_minutes=int(raw["office_min_minutes"]) if raw["office_min_minutes"] else None,
        )

    async def update(self, data: PlanningSettingsUpdate) -> PlanningSettingsRead:
        changes = data.model_dump(exclude_unset=True)
        for field, value in changes.items():
            if value is None:
                stored = ""
            elif field in ("preferred_work_windows", "workdays"):
                stored = json.dumps(value) if value else ""
            else:
                stored = str(value)
            await self._settings.set_value(_key(field), stored)
        logger.info("Planning settings updated: fields=%s", list(changes.keys()))
        return await self.get()
