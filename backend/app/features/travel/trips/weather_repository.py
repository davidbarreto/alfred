from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.trips.tables import TripWeather


class TripWeatherRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_weather(self, trip_id: int) -> list[TripWeather]:
        stmt = select(TripWeather).where(TripWeather.trip_id == trip_id).order_by(TripWeather.city_key, TripWeather.day)
        return list((await self._session.scalars(stmt)).all())

    async def upsert_weather(self, trip_id: int, rows: list[dict[str, Any]]) -> None:
        """Insert the days, overwriting any already saved for the same trip, city and day."""
        if not rows:
            return
        stmt = insert(TripWeather).values([{"trip_id": trip_id, **row} for row in rows])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_travel_trip_weather_day",
            set_={col: getattr(stmt.excluded, col) for col in ("city", "min_c", "max_c", "precip_mm", "source", "fetched_on")}
            | {"updated_at": func.now()},
        )
        await self._session.execute(stmt)
        await self._session.commit()
