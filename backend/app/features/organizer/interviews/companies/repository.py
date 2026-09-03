from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.companies.schemas import CompanyCreate, CompanyFilters, CompanyUpdate
from app.features.organizer.interviews.companies.tables import Company


class CompanyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_company(self, company_id: int) -> Company | None:
        result = await self._session.execute(select(Company).where(Company.id == company_id))
        return result.scalars().first()

    async def get_companies(self, filters: CompanyFilters) -> list[Company]:
        stmt = select(Company)
        if filters.name is not None:
            stmt = stmt.where(Company.name.ilike(f"%{filters.name}%"))
        stmt = stmt.order_by(Company.name).offset(filters.offset).limit(filters.limit)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def create_company(self, data: CompanyCreate) -> Company:
        company = Company(name=data.name, website=data.website, notes=data.notes)
        self._session.add(company)
        await self._session.commit()
        await self._session.refresh(company)
        return company

    async def update_company(self, company_id: int, data: CompanyUpdate) -> Company | None:
        company = await self.get_company(company_id)
        if company is None:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(company, field, value)
        await self._session.commit()
        await self._session.refresh(company)
        return company

    async def delete_company(self, company_id: int) -> None:
        company = await self.get_company(company_id)
        if company is not None:
            await self._session.delete(company)
            await self._session.commit()
