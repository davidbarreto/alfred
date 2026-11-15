from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.travel.links.tables import WebLink


class WebLinkRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_link(self, link_id: int) -> WebLink | None:
        return await self._session.get(WebLink, link_id)

    async def get_links(
        self, trip_id: int | None = None, place_id: int | None = None, city_id: int | None = None,
        country_id: int | None = None,
    ) -> list[WebLink]:
        stmt = select(WebLink)
        if city_id is not None:
            stmt = stmt.where(WebLink.city_id == city_id)
        if country_id is not None:
            stmt = stmt.where(WebLink.country_id == country_id)
        if trip_id is not None:
            stmt = stmt.where(WebLink.trip_id == trip_id)
        if place_id is not None:
            stmt = stmt.where(WebLink.place_id == place_id)
        result = await self._session.execute(stmt.order_by(WebLink.created_at.desc(), WebLink.id.desc()))
        return list(result.scalars().all())

    async def get_link_ids(
        self, trip_id: int | None = None, place_id: int | None = None, city_id: int | None = None,
        country_id: int | None = None,
    ) -> list[int]:
        found = await self.get_links(trip_id=trip_id, place_id=place_id, city_id=city_id, country_id=country_id)
        return [link.id for link in found]

    async def create_link(self, data: dict[str, Any]) -> WebLink:
        link = WebLink(**data)
        self._session.add(link)
        await self._session.commit()
        await self._session.refresh(link)
        return link

    async def update_link(self, link_id: int, data: dict[str, Any]) -> WebLink | None:
        link = await self.get_link(link_id)
        if link is None:
            return None
        for key, value in data.items():
            setattr(link, key, value)
        await self._session.commit()
        await self._session.refresh(link)
        return link

    async def delete_link(self, link_id: int) -> bool:
        link = await self.get_link(link_id)
        if link is None:
            return False
        await self._session.delete(link)
        await self._session.commit()
        return True
