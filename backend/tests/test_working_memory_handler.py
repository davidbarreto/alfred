from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.working_memory import handle_working_memory


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.list = AsyncMock(return_value=[])
    return service


class TestHandleWorkingMemoryList:
    async def test_defaults_to_active_only(self, mock_service):
        await handle_working_memory("list", {}, mock_service)

        called_filters = mock_service.list.call_args.args[0]
        assert called_filters.expired == "active"
        assert called_filters.key_contains is None

    async def test_query_maps_to_key_contains(self, mock_service):
        await handle_working_memory("list", {"query": "focus"}, mock_service)

        called_filters = mock_service.list.call_args.args[0]
        assert called_filters.key_contains == "focus"


class TestHandleWorkingMemoryUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_working_memory("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
