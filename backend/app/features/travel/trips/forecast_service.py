import logging
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.stays.repository import StayRepository
from app.features.travel.trips.forecast import (
    CityForecast, TripForecast, a_year_earlier, cached, days_from_daily, pick_mode,
)
from app.features.travel.trips.repository import TripRepository
from app.integrations.open_meteo.client import OpenMeteoClient
from app.shared.timezone import local_today

logger = logging.getLogger(__name__)


class TripForecastService:
    def __init__(self, session: AsyncSession, client: OpenMeteoClient):
        self._client = client
        self._trips = TripRepository(session)
        self._stays = StayRepository(session)

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

        stays = await self._stays.get_stays(trip_id)
        places: dict[str, object] = {}
        for stay in stays:
            if stay.place.city:
                places.setdefault(stay.place.city.lower(), stay.place)
        if not places:
            return TripForecast(trip_id=trip_id, mode=mode, available=False, message="Add a stay to see the weather")

        start, end = max(trip.start_date, today), trip.end_date
        if mode == "forecast":
            end = min(end, today + timedelta(days=15))
        dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        cities: list[CityForecast] = []
        try:
            for place in places.values():
                coords = await self._coordinates(place)
                if coords is None:
                    continue
                lat, lng = coords
                if mode == "forecast":
                    key = ("forecast", round(lat, 2), round(lng, 2), start, end)
                    days = await cached(key, lambda: self._load(lat, lng, start, end, dates, archive=False))
                else:
                    key = ("climate", round(lat, 2), round(lng, 2), start, end)
                    days = await cached(key, lambda: self._load(lat, lng, a_year_earlier(start), a_year_earlier(end), dates, archive=True))
                cities.append(CityForecast(city=place.city, days=days))
        except Exception as exc:  # Open-Meteo down or rejecting the range: the page just says so
            logger.warning("Trip forecast failed: trip_id=%d error=%s", trip_id, exc)
            return TripForecast(trip_id=trip_id, mode=mode, available=False, message="The weather service is not available")
        logger.debug("Trip forecast: id=%d mode=%s cities=%d", trip_id, mode, len(cities))
        return TripForecast(trip_id=trip_id, mode=mode, available=bool(cities), cities=cities,
                            message=None if cities else "Could not locate the stay cities")

    async def _load(self, lat, lng, start, end, dates, archive):
        daily = await self._client.fetch_range(lat, lng, start, end, archive=archive)
        return days_from_daily(daily, dates)
