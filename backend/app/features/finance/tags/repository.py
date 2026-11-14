from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.tags.tables import FinanceTag
from app.features.finance.tags.schemas import TagCreate, TagUpdate


class TagRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tag(self, tag_id: int) -> FinanceTag | None:
        result = await self._session.execute(select(FinanceTag).where(FinanceTag.id == tag_id))
        return result.scalars().first()

    async def get_tags(self) -> list[FinanceTag]:
        result = await self._session.execute(select(FinanceTag).order_by(FinanceTag.name))
        return list(result.scalars().all())

    async def get_tag_by_name(self, name: str, exclude_id: int | None = None) -> FinanceTag | None:
        """Case-insensitive lookup, so "travel" finds "Travel"."""
        query = select(FinanceTag).where(func.lower(FinanceTag.name) == name.strip().lower())
        if exclude_id is not None:
            query = query.where(FinanceTag.id != exclude_id)
        result = await self._session.execute(query)
        return result.scalars().first()

    async def resolve_tags(self, names: list[str]) -> list[FinanceTag]:
        """Get-or-create every tag by name (case-insensitive: "travel" reuses "Travel"),
        e.g. for wiring TransactionCreate.tags onto a Transaction -- mirrors
        organizer.tags' _resolve_tags pattern, minus the provider_id scoping (finance
        tags aren't a Notion write-through cache). Names repeated in a different case
        within one call resolve to a single tag."""
        tags: list[FinanceTag] = []
        seen: dict[str, FinanceTag] = {}
        for name in names:
            key = name.strip().lower()
            tag = seen.get(key)
            if tag is None:
                tag = await self.get_tag_by_name(name)
                if tag is None:
                    tag = FinanceTag(name=key)
                    self._session.add(tag)
                seen[key] = tag
                tags.append(tag)
        return tags

    async def create_tag(self, data: TagCreate) -> FinanceTag:
        tag = FinanceTag(**data.model_dump())
        self._session.add(tag)
        await self._session.commit()
        await self._session.refresh(tag)
        return tag

    async def update_tag(self, tag_id: int, data: TagUpdate) -> FinanceTag | None:
        tag = await self.get_tag(tag_id)
        if tag is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(tag, field, value)
        await self._session.commit()
        await self._session.refresh(tag)
        return tag

    async def delete_tag(self, tag_id: int) -> bool:
        tag = await self.get_tag(tag_id)
        if tag is None:
            return False
        await self._session.delete(tag)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            raise
        return True
