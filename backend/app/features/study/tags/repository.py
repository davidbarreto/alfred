from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.study.tags.tables import StudyTag


class StudyTagRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tags(self) -> list[StudyTag]:
        result = await self._session.execute(select(StudyTag).order_by(StudyTag.name))
        return list(result.scalars().all())

    async def resolve_tags(self, names: list[str]) -> list[StudyTag]:
        """Get-or-create every tag by name (same pattern as finance.tags)."""
        tags = []
        for name in names:
            result = await self._session.execute(select(StudyTag).where(StudyTag.name == name))
            tag = result.scalars().first()
            if tag is None:
                tag = StudyTag(name=name)
                self._session.add(tag)
            tags.append(tag)
        return tags
