from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.features.core.memories.schemas import (
    MemoryCreate,
    MemoryFilters,
    MemoryRead,
    MemoryUpdate,
)
from app.features.core.memories.service import MemoryService


def _make_memory_orm(**kwargs):
    m = MagicMock()
    m.id = kwargs.get("id", 1)
    m.category = kwargs.get("category", "fact")
    m.content = kwargs.get("content", "Paris is the capital of France")
    m.importance = kwargs.get("importance", 0.8)
    m.confidence = kwargs.get("confidence", 1.0)
    m.active = kwargs.get("active", True)
    m.expires_at = kwargs.get("expires_at", None)
    m.extra_metadata = kwargs.get("extra_metadata", None)
    m.origin_message_id = kwargs.get("origin_message_id", None)
    m.created_at = kwargs.get("created_at", datetime(2026, 1, 1))
    m.updated_at = kwargs.get("updated_at", datetime(2026, 1, 1))
    return m


@pytest.fixture
def service():
    svc = MemoryService.__new__(MemoryService)
    svc._repo = AsyncMock()
    return svc


class TestGet:
    async def test_returns_memory_read_when_found(self, service):
        service._repo.get.return_value = _make_memory_orm()
        result = await service.get(1)
        assert isinstance(result, MemoryRead)
        assert result.id == 1
        assert result.category == "fact"

    async def test_returns_none_when_not_found(self, service):
        service._repo.get.return_value = None
        assert await service.get(999) is None


class TestList:
    async def test_returns_list_of_memory_reads(self, service):
        service._repo.list.return_value = [_make_memory_orm(id=i) for i in range(3)]
        result = await service.list(MemoryFilters())
        assert len(result) == 3
        assert all(isinstance(m, MemoryRead) for m in result)

    async def test_empty_list(self, service):
        service._repo.list.return_value = []
        assert await service.list(MemoryFilters()) == []

    async def test_passes_filters_to_repo(self, service):
        service._repo.list.return_value = []
        filters = MemoryFilters(category="fact", active=True)
        await service.list(filters)
        service._repo.list.assert_called_once_with(filters)


class TestCreate:
    async def test_returns_memory_read(self, service):
        service._repo.create.return_value = _make_memory_orm(content="test memory")
        data = MemoryCreate(category="fact", content="test memory")
        result = await service.create(data)
        assert isinstance(result, MemoryRead)
        assert result.content == "test memory"


class TestUpdate:
    async def test_returns_memory_read_when_found(self, service):
        service._repo.update.return_value = _make_memory_orm(active=False)
        result = await service.update(1, MemoryUpdate(active=False))
        assert isinstance(result, MemoryRead)
        assert result.active is False

    async def test_returns_none_when_not_found(self, service):
        service._repo.update.return_value = None
        assert await service.update(999, MemoryUpdate(content="x")) is None


class TestDelete:
    async def test_returns_true_when_deleted(self, service):
        service._repo.delete.return_value = True
        assert await service.delete(1) is True

    async def test_returns_false_when_not_found(self, service):
        service._repo.delete.return_value = False
        assert await service.delete(999) is False
