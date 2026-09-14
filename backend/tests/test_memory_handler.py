from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.memory import handle_memory


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.list = AsyncMock(return_value=[])
    return service


class TestHandleMemoryList:
    async def test_lists_with_default_filters(self, mock_service):
        await handle_memory("list", {}, mock_service)

        called_filters = mock_service.list.call_args.args[0]
        assert called_filters.category is None
        assert called_filters.active is None
        assert called_filters.q is None


class TestHandleMemorySearch:
    async def test_search_passes_query_as_q(self, mock_service):
        await handle_memory("search", {"query": "birthday"}, mock_service)

        called_filters = mock_service.list.call_args.args[0]
        assert called_filters.q == "birthday"

    async def test_search_requires_query(self, mock_service):
        with pytest.raises(KeyError):
            await handle_memory("search", {}, mock_service)


class TestHandleMemoryUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_memory("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
