from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.assistant.commands.handlers.category import handle_category


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.list = AsyncMock(return_value=[])
    return service


class TestHandleCategoryList:
    async def test_lists_categories(self, mock_service):
        result = await handle_category("list", {}, mock_service)

        mock_service.list.assert_awaited_once_with()
        assert result == []


class TestHandleCategoryUnknown:
    async def test_raises_400_for_unknown_command(self, mock_service):
        with pytest.raises(HTTPException) as exc_info:
            await handle_category("delete", {}, mock_service)
        assert exc_info.value.status_code == 400
