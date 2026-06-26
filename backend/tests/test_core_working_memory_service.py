from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.core.working_memory.schemas import (
    WorkingMemoryCreate,
    WorkingMemoryFilters,
    WorkingMemoryRead,
)
from app.features.core.working_memory.service import WorkingMemoryService


def _make_wm_orm(**kwargs):
    w = MagicMock()
    w.id = kwargs.get("id", 1)
    w.key = kwargs.get("key", "travel_context")
    w.value = kwargs.get("value", "Travelling to Belgium next week")
    w.importance = kwargs.get("importance", 0.9)
    w.expires_at = kwargs.get("expires_at", None)
    w.session_id = kwargs.get("session_id", None)
    w.created_at = kwargs.get("created_at", datetime(2026, 1, 1))
    return w


@pytest.fixture
def service():
    svc = WorkingMemoryService.__new__(WorkingMemoryService)
    svc._repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_working_memory_read_when_found(self, service):
        service._repo.get.return_value = _make_wm_orm()
        result = await service.get(1)
        assert isinstance(result, WorkingMemoryRead)
        assert result.key == "travel_context"

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_active_items_by_default(self, service):
        service._repo.list.return_value = [_make_wm_orm()]
        filters = WorkingMemoryFilters()
        assert filters.active_only is True
        result = await service.list(filters)
        assert len(result) == 1
        assert all(isinstance(w, WorkingMemoryRead) for w in result)

    async def test_passes_session_filter_to_repo(self, service):
        service._repo.list.return_value = []
        filters = WorkingMemoryFilters(session_id=5)
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)

    async def test_passes_key_filter_to_repo(self, service):
        service._repo.list.return_value = [_make_wm_orm(key="language:pending_practice")]
        filters = WorkingMemoryFilters(key="language:pending_practice")
        result = await service.list(filters)
        service._repo.list.assert_called_once_with(filters)
        assert result[0].key == "language:pending_practice"

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        assert await service.list(WorkingMemoryFilters()) == []


class TestCreate:
    async def test_returns_working_memory_read(self, service):
        service._repo.create.return_value = _make_wm_orm(key="mood", value="happy")
        result = await service.create(WorkingMemoryCreate(key="mood", value="happy"))
        assert isinstance(result, WorkingMemoryRead)
        assert result.value == "happy"


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False
