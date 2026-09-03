from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.organizer.interviews.links.schemas import InterviewLinkCreate
from app.features.organizer.interviews.links.service import InterviewLinkService


def _make_link_orm(**kwargs):
    orm = MagicMock()
    orm.id = kwargs.get("id", 1)
    orm.process_id = kwargs.get("process_id", 1)
    orm.url = kwargs.get("url", "https://example.com/job")
    orm.label = kwargs.get("label", None)
    orm.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return orm


@pytest.fixture
def service():
    svc = InterviewLinkService(session=AsyncMock())
    svc._repo = AsyncMock()
    return svc


class TestGetLinks:
    async def test_returns_links_from_repo(self, service):
        service._repo.get_links.return_value = [_make_link_orm(id=1), _make_link_orm(id=2)]
        result = await service.get_links(1)
        service._repo.get_links.assert_called_once_with(1)
        assert [l.id for l in result] == [1, 2]


class TestCreateLink:
    async def test_delegates_to_repo(self, service):
        service._repo.create_link.return_value = _make_link_orm()
        data = InterviewLinkCreate(process_id=1, url="https://example.com/job", label="Job posting")
        result = await service.create_link(data)
        service._repo.create_link.assert_called_once_with(data)
        assert result.url == "https://example.com/job"


class TestDeleteLink:
    async def test_delegates_to_repo(self, service):
        await service.delete_link(1)
        service._repo.delete_link.assert_called_once_with(1)
