import logging
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.legs.repository import LegRepository
from app.features.travel.stays.repository import StayRepository
from app.features.travel.trips.forecast import (
    CityForecast, TripForecast, a_year_earlier, cached, days_from_daily, pick_mode,
)
from app.features.travel.trips.repository import TripRepository
from app.features.travel.zones import to_local
from app.integrations.open_meteo.client import OpenMeteoClient
from app.shared.timezone import local_today

logger = logging.getLogger(__name__)


class TripForecastService:
    def __init__(self, session: AsyncSession, client: OpenMeteoClient):
        self._client = client
        self._trips = TripRepository(session)
        self._stays = StayRepository(session)
        self._legs = LegRepository(session)

    async def _coordinates(self, place) -> tuple[float, float] | None:
        if place.lat is not None and place.lng is not None:
            return place.lat, place.lng
        found = await self._client.geocode(", ".join(p for p in (place.city, place.country) if p))
        return (found["latitude"], found["longitude"]) if found else None

    async def get_forecast(self, trip_id: int) -> TripForecast | None:
        trip = await self._trips.get_trip(trip_id)
        if trip is None:
            return None
        today = local_today()
        mode = pick_mode(trip.start_date, trip.end_date, today)
        if mode == "none":
            return TripForecast(trip_id=trip_id, mode="none", available=False, message="The trip is over")

        places: dict[str, object] = {}
        stay_days: dict[str, set[date]] = {}
        for stay in await self._stays.get_stays(trip_id):
            if stay.place.city:
                key = stay.place.city.lower()
                places.setdefault(key, stay.place)
                check_in, check_out = to_local(stay.check_in_at, stay.timezone).date(), to_local(stay.check_out_at, stay.timezone).date()
                stay_days.setdefault(key, set()).update(check_in + timedelta(days=i) for i in range((check_out - check_in).days + 1))
        # The trip's two ends: where the first leg departs from (that day) and where the last one lands (that day).
        # A city that is also a stay city shares its row.
        legs = await self._legs.get_legs(trip_id)
        if legs:
            first, last = legs[0], max(legs, key=lambda l: l.arrives_at)
            for city, day in ((first.origin, to_local(first.departs_at, first.departs_tz).date()),
                              (last.destination, to_local(last.arrives_at, last.arrives_tz).date())):
                key = city.strip().lower()
                places.setdefault(key, SimpleNamespace(city=city.strip(), country=None, lat=None, lng=None))
                stay_days.setdefault(key, set()).add(day)
        if not places:
            return TripForecast(trip_id=trip_id, mode=mode, available=False, message="Add a stay or a leg to see the weather")

        start, end = max(trip.start_date, today), trip.end_date
        if mode == "forecast":
            end = min(end, today + timedelta(days=15))
        cities: list[CityForecast] = []
        try:
            for city_key, place in places.items():
                # Only the days the trip spends in this city, fetched as one range from its first to its last day.
                wanted = sorted(d for d in stay_days[city_key] if start <= d <= end)
                if not wanted:
                    continue
                first, last = wanted[0], wanted[-1]
                dates = [first + timedelta(days=i) for i in range((last - first).days + 1)]
                coords = await self._coordinates(place)
                if coords is None:
                    continue
                lat, lng = coords
                if mode == "forecast":
                    key = ("forecast", round(lat, 2), round(lng, 2), first, last)
                    days = await cached(key, lambda: self._load(lat, lng, first, last, dates, archive=False))
                else:
                    key = ("climate", round(lat, 2), round(lng, 2), first, last)
                    days = await cached(key, lambda: self._load(lat, lng, a_year_earlier(first), a_year_earlier(last), dates, archive=True))
                cities.append(CityForecast(city=place.city, days=[d for d in days if d.date in stay_days[city_key]]))
        except Exception as exc:  # Open-Meteo down or rejecting the range: the page just says so
            logger.warning("Trip forecast failed: trip_id=%d error=%s", trip_id, exc)
            return TripForecast(trip_id=trip_id, mode=mode, available=False, message="The weather service is not available")
        logger.debug("Trip forecast: id=%d mode=%s cities=%d", trip_id, mode, len(cities))
        return TripForecast(trip_id=trip_id, mode=mode, available=bool(cities), cities=cities,
                            message=None if cities else "Could not locate the stay cities")

    async def _load(self, lat, lng, start, end, dates, archive):
        daily = await self._client.fetch_range(lat, lng, start, end, archive=archive)
        return days_from_daily(daily, dates)
