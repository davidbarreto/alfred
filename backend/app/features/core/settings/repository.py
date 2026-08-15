from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.core.settings.tables import Setting


class SettingRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str) -> Setting | None:
        result = await self._session.execute(select(Setting).where(Setting.key == key))
        return result.scalars().first()

    async def set(self, key: str, value: str) -> Setting:
        stmt = (
            pg_insert(Setting)
            .values(key=key, value=value)
            .on_conflict_do_update(index_elements=[Setting.key], set_={"value": value})
            .returning(Setting)
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        return result.scalars().one()
