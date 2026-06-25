import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.language.grammar_scope.repository import GrammarScopeRepository
from app.features.language.grammar_scope.schemas import (
    GrammarScopeCreate,
    GrammarScopeFilters,
    GrammarScopeRead,
    GrammarScopeUpdate,
)

logger = logging.getLogger(__name__)


class GrammarScopeService:

    def __init__(self, session: AsyncSession) -> None:
        self._repo = GrammarScopeRepository(session)

    async def get_scope(self, scope_id: int) -> GrammarScopeRead | None:
        orm = await self._repo.get_scope(scope_id)
        return GrammarScopeRead.model_validate(orm) if orm else None

    async def get_scopes(self, filters: GrammarScopeFilters) -> list[GrammarScopeRead]:
        scopes = await self._repo.get_scopes(filters)
        return [GrammarScopeRead.model_validate(s) for s in scopes]

    async def create_scope(self, data: GrammarScopeCreate) -> GrammarScopeRead:
        orm = await self._repo.create_scope(data)
        logger.info("Grammar scope created: id=%d track_id=%d value=%r", orm.id, orm.track_id, orm.value)
        return GrammarScopeRead.model_validate(orm)

    async def bulk_create_scopes(self, items: list[GrammarScopeCreate]) -> list[GrammarScopeRead]:
        scopes = await self._repo.bulk_create_scopes(items)
        logger.info("Grammar scopes bulk created: count=%d", len(scopes))
        return [GrammarScopeRead.model_validate(s) for s in scopes]

    async def update_scope(self, scope_id: int, data: GrammarScopeUpdate) -> GrammarScopeRead | None:
        orm = await self._repo.update_scope(scope_id, data)
        if orm is None:
            return None
        logger.info("Grammar scope updated: id=%d status=%r", scope_id, orm.status)
        return GrammarScopeRead.model_validate(orm)

    async def delete_scope(self, scope_id: int) -> None:
        await self._repo.delete_scope(scope_id)
        logger.info("Grammar scope deleted: id=%d", scope_id)
