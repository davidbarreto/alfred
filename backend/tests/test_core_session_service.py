from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.core.sessions.schemas import SessionCreate, SessionFilters, SessionRead
from app.features.core.sessions.service import SessionService


def _make_session_orm(**kwargs):
    s = MagicMock()
    s.id = kwargs.get("id", 1)
    s.source = kwargs.get("source", None)
    s.external_id = kwargs.get("external_id", None)
    s.summary = kwargs.get("summary", None)
    s.last_interaction_at = kwargs.get("last_interaction_at", datetime(2026, 1, 1))
    s.created_at = kwargs.get("created_at", datetime(2026, 1, 1))
    s.finished_at = kwargs.get("finished_at", None)
    return s


@pytest.fixture
def service():
    svc = SessionService.__new__(SessionService)
    svc._repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_session_read_when_found(self, service):
        service._repo.get.return_value = _make_session_orm()
        result = await service.get(1)
        assert isinstance(result, SessionRead)
        assert result.id == 1

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_session_reads(self, service):
        service._repo.list.return_value = [_make_session_orm(id=i) for i in range(2)]
        result = await service.list(SessionFilters())
        assert len(result) == 2
        assert all(isinstance(s, SessionRead) for s in result)

    async def test_passes_active_only_filter(self, service):
        service._repo.list.return_value = []
        filters = SessionFilters(active_only=True)
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)


class TestCreate:
    async def test_returns_session_read(self, service):
        service._repo.create.return_value = _make_session_orm(summary="Morning briefing")
        result = await service.create(SessionCreate(summary="Morning briefing"))
        assert isinstance(result, SessionRead)
        assert result.summary == "Morning briefing"


class TestGetOrCreateActive:
    async def test_returns_existing_active_session(self, service):
        existing = _make_session_orm(id=5, source="telegram", external_id="42")
        service._repo.get_active_by_source.return_value = existing
        service._repo.touch = AsyncMock()
        result = await service.get_or_create_active("telegram", "42")
        assert result.id == 5
        service._repo.touch.assert_called_once_with(5)
        service._repo.create.assert_not_called()

    async def test_creates_new_session_when_none_active(self, service):
        service._repo.get_active_by_source.return_value = None
        new_session = _make_session_orm(id=7, source="telegram", external_id="42")
        service._repo.create.return_value = new_session
        result = await service.get_or_create_active("telegram", "42")
        assert result.id == 7
        service._repo.create.assert_called_once()
        created_data = service._repo.create.call_args[0][0]
        assert created_data.source == "telegram"
        assert created_data.external_id == "42"


class TestFinish:
    async def test_returns_session_read_with_finished_at(self, service):
        service._repo.finish.return_value = _make_session_orm(finished_at=datetime(2026, 1, 1, 12))
        result = await service.finish(1)
        assert isinstance(result, SessionRead)
        assert result.finished_at is not None

    async def test_returns_none_when_not_found(self, service):
        service._repo.finish.return_value = None
        assert await service.finish(999) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False
