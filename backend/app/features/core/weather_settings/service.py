import logging
from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.service import SettingService
from app.features.core.weather_settings.errors import WeatherPlaceInvalidError, WeatherPlaceNotFoundError
from app.features.core.weather_settings.schemas import (
    WeatherChoice,
    WeatherChoices,
    WeatherPlace,
    WeatherSettingsRead,
    WeatherSettingsUpdate,
)
from app.features.organizer.locations.repository import LocationRepository
from app.features.organizer.locations.schemas import LocationFilters
from app.features.organizer.locations.tables import Location
from app.features.location.cities.repository import CityRepository
from app.features.location.cities.schemas import CityFilters

logger = logging.getLogger(__name__)

_KEY_PREFIX = "weather."
FIELDS = ("location_id", "city_id")

# Finds a city by name: (latitude, longitude), or None when it is unknown.
Geocode = Callable[[str], Awaitable[tuple[float, float] | None]]


def _key(field: str) -> str:
    return f"{_KEY_PREFIX}{field}"


def _has_coordinates(location: Location | None) -> bool:
    return location is not None and location.latitude is not None and location.longitude is not None


def _city_label(city) -> str:
    return f"{city.name}, {city.country.name}"


class WeatherSettingsService:
    """Where the weather is looked up: a chosen location, a chosen city, or by default the Home location.

    Stored as `weather.location_id` / `weather.city_id` (at most one). Resolution order: the chosen location's
    coordinates, the chosen city geocoded by name, the Home location's coordinates, else none (weather unavailable).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._settings = SettingService(session)
        self._locations = LocationRepository(session)
        self._cities = CityRepository(session)

    async def _stored(self) -> dict[str, int | None]:
        values: dict[str, int | None] = {}
        for field in FIELDS:
            raw = await self._settings.get_value(_key(field))
            values[field] = int(raw) if raw else None
        return values

    async def _choices(self) -> WeatherChoices:
        locations = await self._locations.list(LocationFilters(active=True, limit=500))
        cities = await self._cities.get_cities(CityFilters())
        return WeatherChoices(
            locations=[WeatherChoice(id=l.id, label=l.name) for l in locations if _has_coordinates(l)],
            cities=[WeatherChoice(id=c.id, label=_city_label(c)) for c in cities],
        )

    async def _usable_location(self, location_id: int | None) -> Location | None:
        """The chosen location while it is still active and has coordinates; else None (falls back to Home)."""
        if location_id is None:
            return None
        location = await self._locations.get(location_id)
        if location is None or not location.active or not _has_coordinates(location):
            logger.warning("Weather location unusable, falling back to Home: location_id=%d", location_id)
            return None
        return location

    async def get(self) -> WeatherSettingsRead:
        stored = await self._stored()
        return WeatherSettingsRead(**stored, place_label=await self._place_label(stored), choices=await self._choices())

    async def _place_label(self, stored: dict[str, int | None]) -> str | None:
        location = await self._usable_location(stored["location_id"])
        if location is not None:
            return location.name
        city = await self._cities.get_city(stored["city_id"]) if stored["city_id"] is not None else None
        if city is not None:
            return _city_label(city)
        home = await self._locations.get_home()
        return f"{home.name} (Home)" if _has_coordinates(home) else None

    async def update(self, data: WeatherSettingsUpdate) -> WeatherSettingsRead:
        changes = data.model_dump(exclude_unset=True)
        if changes.get("location_id") is not None:
            location = await self._locations.get(changes["location_id"])
            if location is None:
                raise WeatherPlaceNotFoundError(f"Location {changes['location_id']} not found")
            if not _has_coordinates(location):
                raise WeatherPlaceInvalidError(
                    f"{location.name} has no coordinates: add them on its page (or a Maps link that carries them)"
                )
            if not location.active:
                raise WeatherPlaceInvalidError(f"{location.name} is archived")
        if changes.get("city_id") is not None and await self._cities.get_city(changes["city_id"]) is None:
            raise WeatherPlaceNotFoundError(f"City {changes['city_id']} not found")
        # Choosing one clears the other, so a single field is enough to switch.
        if changes.get("location_id") is not None:
            changes["city_id"] = None
        if changes.get("city_id") is not None:
            changes["location_id"] = None
        for field, value in changes.items():
            await self._settings.set_value(_key(field), "" if value is None else str(value))
        logger.info("Weather settings updated: fields=%s", sorted(changes))
        return await self.get()

    async def resolve(self, geocode: Geocode | None = None) -> WeatherPlace | None:
        """The place to look the weather up at, or None when nothing has coordinates."""
        stored = await self._stored()
        location = await self._usable_location(stored["location_id"])
        if location is not None:
            return WeatherPlace(
                source="location", label=location.name,
                latitude=float(location.latitude), longitude=float(location.longitude),
            )
        city = await self._cities.get_city(stored["city_id"]) if stored["city_id"] is not None else None
        if city is not None and geocode is not None:
            try:
                found = await geocode(_city_label(city))
            except Exception as exc:
                logger.warning("Weather city geocoding failed: city_id=%d error=%s", city.id, exc)
                found = None
            if found is not None:
                return WeatherPlace(source="city", label=_city_label(city), latitude=found[0], longitude=found[1])
        home = await self._locations.get_home()
        if _has_coordinates(home):
            return WeatherPlace(
                source="home", label=home.name, latitude=float(home.latitude), longitude=float(home.longitude)
            )
        logger.debug("Weather place: none (no chosen place and Home has no coordinates)")
        return None
