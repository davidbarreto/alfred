import pytest
from unittest.mock import AsyncMock, MagicMock
from app.features.finance.tags.service import TagDeletionBlockedError, TagNameConflictError, TagService
from app.features.finance.tags.schemas import TagCreate, TagUpdate, TagRead


def _make_tag_orm(**kwargs):
    t = MagicMock()
    t.id = kwargs.get("id", 1)
    t.name = kwargs.get("name", "Travel")
    return t


@pytest.fixture
def service():
    svc = TagService.__new__(TagService)
    svc._repo = AsyncMock()
    svc._repo.get_tag_by_name.return_value = None
    svc._budget_repo = AsyncMock()
    svc._budget_repo.has_open_tag_target.return_value = False
    return svc


class TestGet:
    async def test_returns_tag_read_when_found(self, service):
        service._repo.get_tag.return_value = _make_tag_orm()
        result = await service.get(1)
        assert isinstance(result, TagRead)
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get_tag.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_tag_reads(self, service):
        service._repo.get_tags.return_value = [_make_tag_orm(id=i) for i in range(3)]
        result = await service.list()
        assert len(result) == 3
        assert all(isinstance(t, TagRead) for t in result)

    async def test_empty_list(self, service):
        service._repo.get_tags.return_value = []
        assert await service.list() == []


class TestCreate:
    async def test_returns_tag_read(self, service):
        service._repo.create_tag.return_value = _make_tag_orm(name="Work")
        result = await service.create(TagCreate(name="Work"))
        assert isinstance(result, TagRead)
        assert result.name == "Work"


class TestNameConflicts:
    async def test_create_rejects_name_taken_in_another_case(self, service):
        service._repo.get_tag_by_name.return_value = _make_tag_orm(name="Travel")
        with pytest.raises(TagNameConflictError):
            await service.create(TagCreate(name="travel"))
        service._repo.create_tag.assert_not_called()

    async def test_rename_rejects_name_taken_by_another_tag(self, service):
        service._repo.get_tag_by_name.return_value = _make_tag_orm(id=2, name="Work")
        with pytest.raises(TagNameConflictError):
            await service.update(1, TagUpdate(name="WORK"))
        service._repo.get_tag_by_name.assert_awaited_once_with("WORK", exclude_id=1)
        service._repo.update_tag.assert_not_called()

    async def test_rename_to_other_case_of_itself_is_allowed(self, service):
        service._repo.update_tag.return_value = _make_tag_orm(name="TRAVEL")
        result = await service.update(1, TagUpdate(name="TRAVEL"))
        assert result.name == "TRAVEL"


class TestUpdate:
    async def test_returns_tag_read_when_found(self, service):
        service._repo.update_tag.return_value = _make_tag_orm(name="Business")
        result = await service.update(1, TagUpdate(name="Business"))
        assert isinstance(result, TagRead)

    async def test_returns_none_when_not_found(self, service):
        service._repo.update_tag.return_value = None
        assert await service.update(999, TagUpdate(name="X")) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.delete_tag.return_value = True
        assert await service.delete(1) is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.delete_tag.return_value = False
        assert await service.delete(999) is False


class TestDeleteWithBudget:
    async def test_blocked_when_tag_has_an_open_budget(self, service):
        service._budget_repo.has_open_tag_target.return_value = True
        with pytest.raises(TagDeletionBlockedError):
            await service.delete(1)
        service._repo.delete_tag.assert_not_called()
