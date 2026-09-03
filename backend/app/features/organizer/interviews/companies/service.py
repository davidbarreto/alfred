from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.organizer.interviews.companies.repository import CompanyRepository
from app.features.organizer.interviews.companies.schemas import (
    CompanyCreate,
    CompanyFilters,
    CompanyRead,
    CompanyUpdate,
)

logger = logging.getLogger(__name__)


class CompanyService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = CompanyRepository(session)

    async def get_company(self, company_id: int) -> CompanyRead | None:
        company = await self._repo.get_company(company_id)
        return CompanyRead.model_validate(company) if company else None

    async def get_companies(self, filters: CompanyFilters) -> list[CompanyRead]:
        companies = await self._repo.get_companies(filters)
        return [CompanyRead.model_validate(c) for c in companies]

    async def create_company(self, data: CompanyCreate) -> CompanyRead:
        company = await self._repo.create_company(data)
        logger.info("Interview company created: id=%d name=%r", company.id, company.name)
        return CompanyRead.model_validate(company)

    async def update_company(self, company_id: int, data: CompanyUpdate) -> CompanyRead | None:
        company = await self._repo.update_company(company_id, data)
        if company is None:
            logger.debug("Interview company update: id=%d not found", company_id)
            return None
        logger.info("Interview company updated: id=%d fields=%s", company_id, list(data.model_dump(exclude_unset=True).keys()))
        return CompanyRead.model_validate(company)

    async def delete_company(self, company_id: int) -> None:
        await self._repo.delete_company(company_id)
        logger.info("Interview company deleted: id=%d", company_id)
