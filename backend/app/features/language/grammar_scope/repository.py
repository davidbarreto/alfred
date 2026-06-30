from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.grammar_scope.tables import GrammarScope
from app.features.language.grammar_scope.schemas import GrammarScopeCreate, GrammarScopeUpdate, GrammarScopeFilters


class GrammarScopeRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_scope(self, scope_id: int) -> GrammarScope | None:
        result = await self._session.execute(
            select(GrammarScope).where(GrammarScope.id == scope_id)
        )
        return result.scalars().first()

    async def get_scopes(self, filters: GrammarScopeFilters) -> list[GrammarScope]:
        query = select(GrammarScope)
        if filters.track_id is not None:
            query = query.where(GrammarScope.track_id == filters.track_id)
        if filters.status != "ALL":
            query = query.where(GrammarScope.status == filters.status)
        query = query.order_by(GrammarScope.priority.asc(), GrammarScope.id.asc()).limit(filters.limit).offset(filters.offset)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create_scope(self, data: GrammarScopeCreate) -> GrammarScope:
        scope = GrammarScope(**data.model_dump())
        self._session.add(scope)
        await self._session.commit()
        await self._session.refresh(scope)
        return scope

    async def update_scope(self, scope_id: int, data: GrammarScopeUpdate) -> GrammarScope | None:
        scope = await self.get_scope(scope_id)
        if scope is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(scope, field, value)
        await self._session.commit()
        await self._session.refresh(scope)
        return scope

    async def delete_scope(self, scope_id: int) -> None:
        scope = await self.get_scope(scope_id)
        if scope:
            await self._session.delete(scope)
            await self._session.commit()

    async def bulk_create_scopes(self, items: list[GrammarScopeCreate]) -> list[GrammarScope]:
        scopes = [GrammarScope(**item.model_dump()) for item in items]
        self._session.add_all(scopes)
        await self._session.commit()
        for scope in scopes:
            await self._session.refresh(scope)
        return scopes
