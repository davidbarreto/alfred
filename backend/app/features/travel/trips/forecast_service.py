import logging
from datetime import date, timedelta
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.legs.repository import LegRepository
from app.features.travel.stays.repository import StayRepository
from app.features.travel.trips.forecast import (
    RAIN_MM, CityForecast, ForecastDay, ForecastMode, TripForecast, a_year_earlier, days_from_daily, pick_mode,
)
from app.features.travel.trips.repository import TripRepository
from app.features.travel.trips.tables import TripWeather
from app.features.travel.trips.weather_repository import TripWeatherRepository
from app.features.travel.zones import to_local
from app.integrations.open_meteo.client import OpenMeteoClient
from app.shared.timezone import local_today

logger = logging.getLogger(__name__)

# Open-Meteo forecasts reach 16 days; ask for one less.
_FORECAST_REACH_DAYS = 15
# The forecast endpoint also serves past days up to 92 days back (no lag); older ones need the archive.
_PAST_REACH_DAYS = 90


class TripForecastService:
    """Weather per trip city, kept in `travel.trip_weather`.

    The first request of each local day asks Open-Meteo for the days that are today or later and overwrites their
    rows; later requests that day read the table. Days that have passed are never refreshed, so they keep the last
    forecast they got, and a finished trip is served from the table alone.
    """

    def __init__(self, session: AsyncSession, client: OpenMeteoClient):
        self._client = client
        self._trips = TripRepository(session)
        self._stays = StayRepository(session)
        self._legs = LegRepository(session)
        self._weather = TripWeatherRepository(session)

    async def _coordinates(self, place) -> tuple[float, float] | None:
        if place.lat is not None and place.lng is not None:
            return place.lat, place.lng
        found = await self._client.geocode(", ".join(p for p in (place.city, place.country) if p))
        return (found["latitude"], found["longitude"]) if found else None

    async def _wanted_days(self, trip_id: int) -> dict[str, tuple[object, set[date]]]:
        """City key -> (place, the days the trip needs weather there): stay days, plus the two ends of the journey."""
        places: dict[str, object] = {}
        days: dict[str, set[date]] = {}
        for stay in await self._stays.get_stays(trip_id):
            if stay.place.city:
                key = stay.place.city.lower()
                places.setdefault(key, stay.place)
                check_in, check_out = to_local(stay.check_in_at, stay.timezone).date(), to_local(stay.check_out_at, stay.timezone).date()
                days.setdefault(key, set()).update(check_in + timedelta(days=i) for i in range((check_out - check_in).days + 1))
        # The first leg's origin on its departure day and the last leg's destination on its arrival day.
        # A city that is also a stay city shares its row.
        legs = await self._legs.get_legs(trip_id)
        if legs:
            first, last = legs[0], max(legs, key=lambda l: l.arrives_at)
            for city, day in ((first.origin, to_local(first.departs_at, first.departs_tz).date()),
                              (last.destination, to_local(last.arrives_at, last.arrives_tz).date())):
                key = city.strip().lower()
                places.setdefault(key, SimpleNamespace(city=city.strip(), country=None, lat=None, lng=None))
                days.setdefault(key, set()).add(day)
        return {key: (places[key], days[key]) for key in places}

    async def get_forecast(self, trip_id: int) -> TripForecast | None:
        trip = await self._trips.get_trip(trip_id)
        if trip is None:
            return None
        today = local_today()
        wanted = await self._wanted_days(trip_id)
        saved = {(r.city_key, r.day): r for r in await self._weather.get_weather(trip_id)}

        finished = trip.end_date < today
        mode: ForecastMode = "none"
        failed = False
        if not finished:
            if not wanted:
                return TripForecast(trip_id=trip_id, mode="none", available=False, message="Add a stay or a leg to see the weather")
            mode = pick_mode(trip.start_date, today)
            last_day = min(trip.end_date, today + timedelta(days=_FORECAST_REACH_DAYS)) if mode == "forecast" else trip.end_date
            try:
                if await self._refresh(trip_id, wanted, saved, mode, today, last_day):
                    saved = {(r.city_key, r.day): r for r in await self._weather.get_weather(trip_id)}
            except Exception as exc:  # Open-Meteo down or rejecting the range: the saved days (if any) are shown
                failed = True
                logger.warning("Trip forecast failed: trip_id=%d error=%s", trip_id, exc)
            shown_until = last_day
        else:
            shown_until = trip.end_date
            try:
                if await self._backfill(trip_id, wanted, saved, today, trip.end_date):
                    saved = {(r.city_key, r.day): r for r in await self._weather.get_weather(trip_id)}
            except Exception as exc:  # the archive is unreachable: nothing is saved and the next request tries again
                failed = True
                logger.warning("Trip weather backfill failed: trip_id=%d error=%s", trip_id, exc)

        cities: list[CityForecast] = []
        rows: list[TripWeather] = []
        for key, (place, days) in wanted.items():
            city_rows = [saved[key, d] for d in sorted(days) if d <= shown_until and (key, d) in saved]
            if city_rows:
                rows.extend(city_rows)
                cities.append(CityForecast(city=place.city, days=[_to_day(r) for r in city_rows]))

        if finished:
            if not cities:
                return TripForecast(trip_id=trip_id, mode="none", available=False, finished=True)
            sources = {r.source for r in rows}
            mode = sources.pop() if len(sources) == 1 else "mixed"
        if not cities:
            message = "The weather service is not available" if failed else "Could not locate the trip cities"
            return TripForecast(trip_id=trip_id, mode=mode, available=False, message=message)
        logger.debug("Trip forecast: id=%d mode=%s cities=%d finished=%s", trip_id, mode, len(cities), finished)
        return TripForecast(trip_id=trip_id, mode=mode, available=True, finished=finished, cities=cities,
                            as_of=max(r.fetched_on for r in rows))

    async def _refresh(self, trip_id: int, wanted: dict, saved: dict, mode: ForecastMode, today: date, last_day: date) -> bool:
        """Fetch the days from today on that were not fetched today and save them. True when rows changed."""
        changed = False
        for key, (place, days) in wanted.items():
            stale = sorted(d for d in days if today <= d <= last_day
                           and ((key, d) not in saved or saved[key, d].fetched_on < today))
            if not stale:
                continue
            coords = await self._coordinates(place)
            if coords is None:
                continue
            first, last = stale[0], stale[-1]
            dates = [first + timedelta(days=i) for i in range((last - first).days + 1)]
            if mode == "forecast":
                loaded = await self._load(*coords, first, last, dates, archive=False)
            else:
                loaded = await self._load(*coords, a_year_earlier(first), a_year_earlier(last), dates, archive=True)
            await self._weather.upsert_weather(trip_id, [
                {"city_key": key, "city": place.city, "day": d.date, "min_c": d.min_c, "max_c": d.max_c,
                 "precip_mm": d.precip_mm, "source": mode, "fetched_on": today}
                for d in loaded if d.date in stale])
            logger.info("Trip weather saved: trip_id=%d city=%s days=%d source=%s", trip_id, place.city, len(stale), mode)
            changed = True
        return changed

    async def _backfill(self, trip_id: int, wanted: dict, saved: dict, today: date, last_day: date) -> bool:
        """For a finished trip, fetch the days that were never saved and save them as actual weather. True when rows were added.

        Days within the forecast endpoint's past reach come from it (it has no lag); older ones come from the
        archive, which lags a few days. A day without values is left unsaved and asked for again next time; a day
        with values is saved for good and never fetched again.
        """
        recent_from = today - timedelta(days=_PAST_REACH_DAYS)
        changed = False
        for key, (place, days) in wanted.items():
            missing = sorted(d for d in days if d <= last_day and (key, d) not in saved)
            coords = await self._coordinates(place) if missing else None
            if coords is None:
                continue
            for archive, group in ((True, [d for d in missing if d < recent_from]), (False, [d for d in missing if d >= recent_from])):
                if not group:
                    continue
                dates = [group[0] + timedelta(days=i) for i in range((group[-1] - group[0]).days + 1)]
                loaded = await self._load(*coords, group[0], group[-1], dates, archive=archive)
                rows = [{"city_key": key, "city": place.city, "day": d.date, "min_c": d.min_c, "max_c": d.max_c,
                         "precip_mm": d.precip_mm, "source": "actual", "fetched_on": today}
                        for d in loaded if d.date in group and d.max_c is not None]
                if rows:
                    await self._weather.upsert_weather(trip_id, rows)
                    logger.info("Trip weather backfilled: trip_id=%d city=%s days=%d", trip_id, place.city, len(rows))
                    changed = True
        return changed

    async def _load(self, lat, lng, start, end, dates, archive):
        daily = await self._client.fetch_range(lat, lng, start, end, archive=archive)
        return days_from_daily(daily, dates)


def _to_day(row: TripWeather) -> ForecastDay:
    return ForecastDay(date=row.day, min_c=row.min_c, max_c=row.max_c, precip_mm=row.precip_mm,
                       rain=(row.precip_mm or 0) >= RAIN_MM)
