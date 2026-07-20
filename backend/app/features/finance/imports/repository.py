from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.imports.schemas import ImportRuleCreate, ImportRuleFilters, ImportRuleUpdate
from app.features.finance.imports.tables import ImportBatch, ImportRule


class ImportRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_rules(self) -> list[ImportRule]:
        """All rules in match precedence order -- this is what categorization uses,
        so the first rule (lowest position) matching a description wins."""
        result = await self._session.execute(
            select(ImportRule).order_by(ImportRule.position)
        )
        return list(result.scalars().all())

    async def list_rules_page(self, filters: ImportRuleFilters) -> list[ImportRule]:
        query = select(ImportRule)
        if filters.sort == "precedence":
            query = query.order_by(ImportRule.position.asc())
        else:
            query = query.order_by(ImportRule.id.desc())
        if filters.pattern:
            query = query.where(ImportRule.pattern.ilike(f"%{filters.pattern}%"))
        if filters.mode:
            query = query.where(ImportRule.mode == filters.mode)
        if filters.category_id is not None:
            query = query.where(ImportRule.category_id == filters.category_id)
        query = query.offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_rule(self, rule_id: int) -> ImportRule | None:
        result = await self._session.execute(
            select(ImportRule).where(ImportRule.id == rule_id)
        )
        return result.scalars().first()

    async def get_rules_by_ids(self, rule_ids: list[int]) -> list[ImportRule]:
        result = await self._session.execute(
            select(ImportRule).where(ImportRule.id.in_(rule_ids))
        )
        return list(result.scalars().all())

    async def next_position(self) -> int:
        """Position for a newly created rule: appended after every existing rule, so it
        starts out as the lowest-precedence match until someone reorders it."""
        result = await self._session.execute(select(func.max(ImportRule.position)))
        current_max = result.scalar()
        return 0 if current_max is None else current_max + 1

    async def create_rule(self, data: ImportRuleCreate) -> ImportRule:
        rule = ImportRule(**data.model_dump())
        rule.position = await self.next_position()
        self._session.add(rule)
        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    async def update_rule(self, rule_id: int, data: ImportRuleUpdate) -> ImportRule | None:
        rule = await self.get_rule(rule_id)
        if rule is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(rule, field, value)
        await self._session.commit()
        await self._session.refresh(rule)
        return rule

    async def delete_rule(self, rule_id: int) -> bool:
        result = await self._session.execute(
            select(ImportRule).where(ImportRule.id == rule_id)
        )
        rule = result.scalars().first()
        if rule is None:
            return False
        await self._session.delete(rule)
        await self._session.commit()
        return True

    async def get_batch(self, batch_id: int) -> ImportBatch | None:
        result = await self._session.execute(
            select(ImportBatch).where(ImportBatch.id == batch_id)
        )
        return result.scalars().first()

    async def list_batches(self) -> list[ImportBatch]:
        result = await self._session.execute(
            select(ImportBatch).order_by(ImportBatch.created_at.desc())
        )
        return list(result.scalars().all())

    async def add_batch(self, batch: ImportBatch) -> ImportBatch:
        """Add batch to session without committing. Caller is responsible for commit."""
        self._session.add(batch)
        await self._session.flush()
        return batch

    def add_rule(self, rule: ImportRule) -> ImportRule:
        """Add rule to session without committing. Caller is responsible for commit."""
        self._session.add(rule)
        return rule

    async def delete_batch(self, batch_id: int) -> bool:
        batch = await self.get_batch(batch_id)
        if batch is None:
            return False
        await self._session.delete(batch)
        await self._session.commit()
        return True

    async def commit(self) -> None:
        await self._session.commit()
