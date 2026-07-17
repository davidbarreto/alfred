from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.finance.imports.schemas import ImportRuleCreate
from app.features.finance.imports.tables import ImportBatch, ImportRule


class ImportRepository:

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_rules(self) -> list[ImportRule]:
        result = await self._session.execute(
            select(ImportRule).order_by(ImportRule.id)
        )
        return list(result.scalars().all())

    async def create_rule(self, data: ImportRuleCreate) -> ImportRule:
        rule = ImportRule(**data.model_dump())
        self._session.add(rule)
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
