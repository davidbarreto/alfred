from sqlalchemy import select
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

    async def resolve_tags(self, names: list[str]) -> list[FinanceTag]:
        """Get-or-create every tag by name, e.g. for wiring TransactionCreate.tags
        onto a Transaction -- mirrors organizer.tags' _resolve_tags pattern, minus
        the provider_id scoping (finance tags aren't a Notion write-through cache)."""
        tags = []
        for name in names:
            result = await self._session.execute(select(FinanceTag).where(FinanceTag.name == name))
            tag = result.scalars().first()
            if tag is None:
                tag = FinanceTag(name=name)
                self._session.add(tag)
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
