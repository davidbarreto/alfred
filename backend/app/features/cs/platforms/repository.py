from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.platforms.schemas import PlatformCreate, PlatformFilters, PlatformUpdate
from app.features.cs.platforms.tables import Platform


class PlatformRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_platform(self, platform_id: int) -> Platform | None:
        result = await self._session.execute(select(Platform).where(Platform.id == platform_id))
        return result.scalars().first()

    async def get_platform_by_code(self, code: str) -> Platform | None:
        result = await self._session.execute(select(Platform).where(Platform.code == code))
        return result.scalars().first()

    async def get_platforms(self, filters: PlatformFilters) -> list[Platform]:
        query = select(Platform)
        if filters.sync_enabled_only:
            query = query.where(Platform.sync_enabled.is_(True))
        query = query.order_by(Platform.code)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create_platform(self, data: PlatformCreate) -> Platform:
        platform = Platform(**data.model_dump())
        self._session.add(platform)
        await self._session.commit()
        await self._session.refresh(platform)
        return platform

    async def update_platform(self, platform_id: int, data: PlatformUpdate) -> Platform | None:
        platform = await self.get_platform(platform_id)
        if platform is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(platform, field, value)
        await self._session.commit()
        await self._session.refresh(platform)
        return platform
