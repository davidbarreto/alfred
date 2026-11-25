import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.location.places.repository import PlaceRepository
from app.features.location.cities.schemas import CityRef
from app.features.travel.settings_schemas import (
    DEFAULT_CHARGE_LINK_LEAD_DAYS,
    DEFAULT_CHARGE_LINK_TAIL_DAYS,
    DEFAULT_CHECK_IN_OPENS_HOURS,
    DEFAULT_CHECKLIST_NUDGE_DAYS,
    DEFAULT_LEAVE_HOME_LEAD_MIN,
    DEFAULT_LONG_WAIT_HOURS,
    DEFAULT_RAIN_MM,
    DEFAULT_TIGHT_CONNECTION_MIN,
    TravelSettingsRead,
    TravelSettingsUpdate,
)
from app.features.travel.trips.home import HOME_FIELDS
from app.features.travel.trips.repository import TripRepository
from app.shared.utils.timezone import local_today

logger = logging.getLogger(__name__)

_KEY_PREFIX = "travel."

# Stored in core.settings as "travel.<field>"; a missing row falls back to the default below.
DEFAULT_AIRPORT_BUFFER_MIN = 120
DEFAULT_HOME_TO_AIRPORT_MIN = 45
DEFAULT_MAX_VISITS_PER_DAY = 4
DEFAULT_VISIT_DURATION_MIN = 90
DEFAULT_UNPAID_LEG_DAYS = 30
DEFAULTS: dict[str, int | float | bool] = {
    "airport_buffer_min": DEFAULT_AIRPORT_BUFFER_MIN,
    "home_to_airport_min": DEFAULT_HOME_TO_AIRPORT_MIN,
    "max_visits_per_day": DEFAULT_MAX_VISITS_PER_DAY,
    "visit_duration_min": DEFAULT_VISIT_DURATION_MIN,
    "unpaid_leg_days": DEFAULT_UNPAID_LEG_DAYS,
    "snooze_other_events": False,
    "leave_home_lead_min": DEFAULT_LEAVE_HOME_LEAD_MIN,
    "check_in_opens_hours": DEFAULT_CHECK_IN_OPENS_HOURS,
    "checklist_nudge_days": DEFAULT_CHECKLIST_NUDGE_DAYS,
    "tight_connection_min": DEFAULT_TIGHT_CONNECTION_MIN,
    "long_wait_hours": DEFAULT_LONG_WAIT_HOURS,
    "rain_mm": DEFAULT_RAIN_MM,
    "charge_link_lead_days": DEFAULT_CHARGE_LINK_LEAD_DAYS,
    "charge_link_tail_days": DEFAULT_CHARGE_LINK_TAIL_DAYS,
}


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class TravelSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)
        self._trips = TripRepository(session)
        self._places = PlaceRepository(session)

    async def get(self) -> TravelSettingsRead:
        values: dict[str, int | str | bool | None] = {}
        for field, default in DEFAULTS.items():
            raw = await self._settings.get_value(_key(field))
            if isinstance(default, bool):
                values[field] = raw == "1" if raw else default
            else:
                values[field] = type(default)(raw) if raw else default
        # Home's address and city live on the Home place (location.places); trips only read them.
        home = await self._places.get_home()
        if home is not None:
            values.update(
                home_address=home.address, home_city_id=home.city_id, home_city=CityRef.model_validate(home.city),
                home=", ".join(filter(None, [home.address, home.city.name])), home_place_id=home.id,
            )
        return TravelSettingsRead(**values)

    async def update(self, data: TravelSettingsUpdate) -> TravelSettingsRead:
        # null leaves a value as it is (the home fields can't be sent at all: the schema refuses them).
        changes = {f: v for f, v in data.model_dump(exclude_unset=True).items() if v is not None}
        await self._snapshot_changed_homes(changes)
        for field, value in changes.items():
            stored = ("1" if value else "0") if isinstance(value, bool) else ("" if value is None else str(value).strip())
            await self._settings.set_value(_key(field), stored)
        logger.info("Travel settings updated: fields=%s", list(changes.keys()))
        return await self.get()

    async def _snapshot_changed_homes(self, changes: dict) -> None:
        """Before a home setting changes, give each trip that has already started the old value it was planned with.

        Only trips whose own column is still NULL get it, and an old value that was never set is not copied: upcoming
        trips keep following the setting. The home address and city are not settings any more: location's `PlaceService`
        snapshots them when the Home place's address or city changes.
        """
        current = await self.get()
        today = local_today()
        for field in HOME_FIELDS:
            if field not in changes or changes[field] == getattr(current, field):
                continue
            old = getattr(current, field)
            if old is None:
                continue
            count = await self._trips.snapshot_home_value(field, old, today)
            logger.info("Travel home setting changed: field=%s trips_keeping_old_value=%d", field, count)
