from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.interviews.companies.schemas import CompanyCreate, CompanyFilters, CompanyUpdate
from app.features.organizer.interviews.companies.service import CompanyService


def _make_company_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.name = kwargs.get("name", "Acme Corp")
    orm.website = kwargs.get("website", None)
    orm.notes = kwargs.get("notes", None)
    return orm


@pytest.fixture
def service():
    svc = CompanyService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestGetCompany:
    async def test_returns_none_when_not_found(self, service):
        service._repo.get_company.return_value = None
        result = await service.get_company(999)
        assert result is None

    async def test_returns_read_schema_when_found(self, service):
        service._repo.get_company.return_value = _make_company_orm()
        result = await service.get_company(1)
        assert result.name == "Acme Corp"


class TestGetCompanies:
    async def test_returns_companies_from_repo(self, service):
        service._repo.get_companies.return_value = [_make_company_orm(id=1), _make_company_orm(id=2)]
        filters = CompanyFilters(limit=100, offset=0, name=None)
        result = await service.get_companies(filters)
        service._repo.get_companies.assert_called_once_with(filters)
        assert [c.id for c in result] == [1, 2]


class TestCreateCompany:
    async def test_delegates_to_repo(self, service):
        service._repo.create_company.return_value = _make_company_orm()
        data = CompanyCreate(name="Acme Corp")
        result = await service.create_company(data)
        service._repo.create_company.assert_called_once_with(data)
        assert result.name == "Acme Corp"


class TestUpdateCompany:
    async def test_returns_none_when_not_found(self, service):
        service._repo.update_company.return_value = None
        result = await service.update_company(999, CompanyUpdate(name="New"))
        assert result is None

    async def test_returns_updated_when_found(self, service):
        service._repo.update_company.return_value = _make_company_orm(name="New Name")
        result = await service.update_company(1, CompanyUpdate(name="New Name"))
        assert result.name == "New Name"


class TestDeleteCompany:
    async def test_delegates_to_repo(self, service):
        await service.delete_company(1)
        service._repo.delete_company.assert_called_once_with(1)
