from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.location.cities.tables import City
from app.features.location.countries.tables import Country
from app.features.location.places.constants import HOME_KIND
from app.features.location.places.tables import Place


class MapRepository:
    """Column-only reads for the map: no ORM objects, one query per layer."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def city_country_id(self, city_id: int) -> int | None:
        return await self._session.scalar(select(City.country_id).where(City.id == city_id))

    async def country_exists(self, country_id: int) -> bool:
        return await self._session.scalar(select(Country.id).where(Country.id == country_id)) is not None

    async def home_city_id(self) -> int | None:
        return await self._session.scalar(select(Place.city_id).where(Place.kind == HOME_KIND))

    async def countries(self, country_id: int | None) -> list[dict[str, Any]]:
        stmt = (
            select(Country.id, Country.name, Country.code, func.count(City.id).label("city_count"))
            .outerjoin(City, City.country_id == Country.id)
            .group_by(Country.id)
            .order_by(func.lower(Country.name), Country.id)
        )
        if country_id is not None:
            stmt = stmt.where(Country.id == country_id)
        return [dict(row._mapping) for row in await self._session.execute(stmt)]

    def _city_scope(self, stmt, country_id: int | None, city_id: int | None):
        if city_id is not None:
            return stmt.where(City.id == city_id)
        if country_id is not None:
            return stmt.where(City.country_id == country_id)
        return stmt

    async def cities(self, country_id: int | None, city_id: int | None) -> list[dict[str, Any]]:
        stmt = select(City.id, City.name, City.country_id, City.latitude, City.longitude).where(City.latitude.is_not(None))
        stmt = self._city_scope(stmt, country_id, city_id).order_by(func.lower(City.name), City.id)
        return [dict(row._mapping) for row in await self._session.execute(stmt)]

    async def cities_without_coordinates(self, country_id: int | None, city_id: int | None) -> int:
        stmt = self._city_scope(select(func.count(City.id)).where(City.latitude.is_(None)), country_id, city_id)
        return await self._session.scalar(stmt) or 0

    def _places_scope(self, stmt, country_id: int | None, city_id: int | None):
        stmt = stmt.join(City, City.id == Place.city_id).where(Place.active.is_(True))
        return self._city_scope(stmt, country_id, city_id)

    async def places(self, country_id: int | None, city_id: int | None) -> list[dict[str, Any]]:
        stmt = select(
            Place.id, Place.name, Place.kind, Place.city_id, City.name.label("city_name"), Place.latitude,
            Place.longitude, Place.maps_url,
        ).where(Place.latitude.is_not(None))
        stmt = self._places_scope(stmt, country_id, city_id).order_by(func.lower(Place.name), Place.id)
        return [dict(row._mapping) for row in await self._session.execute(stmt)]

    async def places_without_coordinates(self, country_id: int | None, city_id: int | None) -> int:
        stmt = self._places_scope(select(func.count(Place.id)).where(Place.latitude.is_(None)), country_id, city_id)
        return await self._session.scalar(stmt) or 0
