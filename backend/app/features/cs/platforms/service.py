import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.cs.platforms.repository import PlatformRepository
from app.features.cs.platforms.schemas import PlatformCreate, PlatformFilters, PlatformRead, PlatformUpdate

logger = logging.getLogger(__name__)


class PlatformService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = PlatformRepository(session)

    async def get_platform(self, platform_id: int) -> PlatformRead | None:
        orm = await self._repo.get_platform(platform_id)
        return PlatformRead.model_validate(orm) if orm else None

    async def get_platform_by_code(self, code: str) -> PlatformRead | None:
        orm = await self._repo.get_platform_by_code(code)
        return PlatformRead.model_validate(orm) if orm else None

    async def get_platforms(self, filters: PlatformFilters) -> list[PlatformRead]:
        platforms = await self._repo.get_platforms(filters)
        return [PlatformRead.model_validate(p) for p in platforms]

    async def create_platform(self, data: PlatformCreate) -> PlatformRead:
        orm = await self._repo.create_platform(data)
        logger.info("Platform created: id=%d code=%r", orm.id, orm.code)
        return PlatformRead.model_validate(orm)

    async def update_platform(self, platform_id: int, data: PlatformUpdate) -> PlatformRead | None:
        orm = await self._repo.update_platform(platform_id, data)
        if orm is None:
            return None
        logger.info("Platform updated: id=%d fields=%s", platform_id, list(data.model_dump(exclude_unset=True).keys()))
        return PlatformRead.model_validate(orm)
