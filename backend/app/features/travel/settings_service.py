import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.organizer.locations.repository import LocationRepository
from app.features.travel.cities.repository import CityRepository
from app.features.travel.cities.schemas import CityRef
from app.features.travel.errors import TravelNotFoundError
from app.features.travel.settings_schemas import TravelSettingsRead, TravelSettingsUpdate
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
_DEFAULTS = {
    "airport_buffer_min": DEFAULT_AIRPORT_BUFFER_MIN,
    "home_to_airport_min": DEFAULT_HOME_TO_AIRPORT_MIN,
    "max_visits_per_day": DEFAULT_MAX_VISITS_PER_DAY,
    "visit_duration_min": DEFAULT_VISIT_DURATION_MIN,
    "unpaid_leg_days": DEFAULT_UNPAID_LEG_DAYS,
}


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


class TravelSettingsService:

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)
        self._cities = CityRepository(session)
        self._trips = TripRepository(session)
        self._locations = LocationRepository(session)

    async def get(self) -> TravelSettingsRead:
        values: dict[str, int | str | bool | None] = {}
        for field, default in _DEFAULTS.items():
            raw = await self._settings.get_value(_key(field))
            values[field] = int(raw) if raw else default
        values["snooze_other_events"] = (await self._settings.get_value(_key("snooze_other_events"))) == "1"
        # The address lives on the Home location (organizer.locations); trips only read it.
        home = await self._locations.get_home()
        values["home_address"] = home.address if home else None
        raw_city = await self._settings.get_value(_key("home_city_id"))
        city = await self._cities.get_city(int(raw_city)) if raw_city else None
        values["home_city_id"] = city.id if city else None
        values["home_city"] = CityRef.model_validate(city) if city else None
        return TravelSettingsRead(**values)

    async def update(self, data: TravelSettingsUpdate) -> TravelSettingsRead:
        sent = data.model_dump(exclude_unset=True)
        # Only the home city may be cleared with null; the numbers and flags ignore it.
        changes = {f: v for f, v in sent.items() if v is not None or f == "home_city_id"}
        if changes.get("home_city_id") is not None and await self._cities.get_city(changes["home_city_id"]) is None:
            raise TravelNotFoundError(f"City {changes['home_city_id']} not found")
        await self._snapshot_changed_homes(changes)
        for field, value in changes.items():
            if field == "home_city_id":
                await self._settings.set_value(_key(field), "" if value is None else str(value))
                continue
            stored = ("1" if value else "0") if isinstance(value, bool) else ("" if value is None else str(value).strip())
            await self._settings.set_value(_key(field), stored)
        logger.info("Travel settings updated: fields=%s", list(changes.keys()))
        return await self.get()

    async def _snapshot_changed_homes(self, changes: dict) -> None:
        """Before a home setting changes, give each trip that has already started the old value it was planned with.

        Only trips whose own column is still NULL get it, and an old value that was never set is not copied: upcoming
        trips keep following the setting. The home address is not a setting any more: `LocationService` snapshots it
        when the Home location's address changes.
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
