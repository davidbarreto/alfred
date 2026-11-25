import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.locations.travel_time_service import LocationTravelTimeService
from app.features.planning.schemas import (
    DEFAULT_ASSUMED_ESTIMATE_MINUTES,
    DEFAULT_BACKLOG_STALE_DAYS,
    DEFAULT_DUE_LOOKAHEAD_DAYS,
    DEFAULT_SHOPPING_RUN_MINUTES,
    DEFAULT_STUDY_ITEMS_PER_PLAN,
    DEFAULT_TRAVEL_MINUTES,
    DEFAULT_WALK_TOLERANCE_MINUTES,
    DEFAULT_WORKDAYS,
    PlanningSettingsRead,
    PlanningSettingsUpdate,
)

logger = logging.getLogger(__name__)

_KEY_PREFIX = "planning."

# Generic defaults; nothing personal is seeded. A missing or blank row means "use the default", and a field
# that is not here (wake/sleep time, office days and minutes, conventions) is simply unset.
DEFAULTS: dict[str, int | str | list[str]] = {
    "work_target_minutes": 480,
    "preferred_work_windows": [],
    "workdays": list(DEFAULT_WORKDAYS),
    "work_tag": "work",
    "office_tag": "office",
    "default_travel_minutes": DEFAULT_TRAVEL_MINUTES,
    "walk_tolerance_minutes": DEFAULT_WALK_TOLERANCE_MINUTES,
    "backlog_stale_days": DEFAULT_BACKLOG_STALE_DAYS,
    "due_lookahead_days": DEFAULT_DUE_LOOKAHEAD_DAYS,
    "assumed_estimate_minutes": DEFAULT_ASSUMED_ESTIMATE_MINUTES,
    "shopping_run_minutes": DEFAULT_SHOPPING_RUN_MINUTES,
    "study_items_per_plan": DEFAULT_STUDY_ITEMS_PER_PLAN,
}
# Plain numbers read with their default from DEFAULTS.
_NUMBER_FIELDS = (
    "default_travel_minutes", "walk_tolerance_minutes", "backlog_stale_days", "due_lookahead_days",
    "assumed_estimate_minutes", "shopping_run_minutes", "study_items_per_plan",
)


def _int_or(raw: str | None, default: int | None) -> int | None:
    return int(raw) if raw else default


def _list_or(raw: str | None, default: list[str]) -> list[str]:
    return json.loads(raw) if raw else list(default)


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class PlanningSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)
        # Travel times are rows between locations, not a setting; the old list shape is kept for clients.
        self._travel_times = LocationTravelTimeService(session)

    async def get(self) -> PlanningSettingsRead:
        raw = {
            field: await self._settings.get_value(_key(field))
            for field in PlanningSettingsRead.model_fields if field != "travel_times"
        }
        return PlanningSettingsRead(
            wake_time=raw["wake_time"] or None,
            sleep_time=raw["sleep_time"] or None,
            work_target_minutes=_int_or(raw["work_target_minutes"], DEFAULTS["work_target_minutes"]),
            preferred_work_windows=_list_or(raw["preferred_work_windows"], DEFAULTS["preferred_work_windows"]),
            workdays=_list_or(raw["workdays"], DEFAULTS["workdays"]),
            work_tag=raw["work_tag"] or DEFAULTS["work_tag"],
            office_tag=raw["office_tag"] or DEFAULTS["office_tag"],
            office_days_per_week=_int_or(raw["office_days_per_week"], None),
            office_min_minutes=_int_or(raw["office_min_minutes"], None),
            conventions=raw["conventions"] or None,
            travel_times=await self._travel_times.as_preferences(),
            **{field: _int_or(raw[field], DEFAULTS[field]) for field in _NUMBER_FIELDS},
        )

    async def update(self, data: PlanningSettingsUpdate) -> PlanningSettingsRead:
        changes = data.model_dump(exclude_unset=True)
        if "travel_times" in changes:
            # The whole list replaces every travel time; null or empty clears them. Unknown names become locations.
            await self._travel_times.replace_from_preferences(
                (t.origin, t.place, t.mode, t.minutes) for t in data.travel_times or []
            )
        for field, value in changes.items():
            if field == "travel_times":
                continue
            if value is None:
                stored = ""
            elif field in ("preferred_work_windows", "workdays"):
                stored = json.dumps(value) if value else ""
            else:
                stored = str(value)
            await self._settings.set_value(_key(field), stored)
        logger.info("Planning settings updated: fields=%s", list(changes.keys()))
        return await self.get()
